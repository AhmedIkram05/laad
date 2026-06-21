from datetime import datetime, timedelta
import json
from psycopg2.extras import RealDictCursor
from backend.src.database.connection import get_conn, release_conn

_CLASSIFIER_DESCRIPTIONS = {
    "A3": {
        "explanation": (
            "ML classifier detected JVM memory leak pattern with confidence {confidence:.2f} "
            "(Isolation Forest score: {if_score:.3f}). "
            "Heap usage trend and GC behavior match trained A3 signature. "
            "Review terminal handler JVM metrics for this ATM to confirm."
        ),
        "operation_impact": "Backend transaction processing is unstable and at risk of service interruption across affected ATM flows.",
        "recommendation": (
            "Inspect JVM heap usage trends for this ATM's terminal handler, "
            "review recent deployments for memory-intensive changes, "
            "and schedule a controlled restart if heap growth continues."
        ),
    },
    "A4": {
        "explanation": (
            "ML classifier detected container restart loop pattern with confidence {confidence:.2f} "
            "(Isolation Forest score: {if_score:.3f}). "
            "Restart and startup metrics match trained A4 signature. "
            "Review GCP container logs for this ATM to confirm."
        ),
        "operation_impact": "Service would be unstable which may interrupt or delay transaction handling across multiple ATM sessions.",
        "recommendation": (
            "Investigate the crash source from container logs, "
            "validate memory and resource limits in Kubernetes, "
            "and stabilize the service before returning it to normal traffic."
        ),
    },
    "A5": {
        "explanation": (
            "ML classifier detected high response time spike pattern with confidence {confidence:.2f} "
            "(Isolation Forest score: {if_score:.3f}). "
            "Latency and success rate features match trained A5 signature. "
            "Review Kafka metrics and ATM application logs for this ATM to confirm."
        ),
        "operation_impact": "Customers may experience slow responses, failed transactions, and degraded ATM service quality.",
        "recommendation": (
            "Investigate latency sources (database queries, external services, network), "
            "review ATM backend service health, "
            "and check for recent deployments that may have introduced performance regressions."
        ),
    },
    "A6": {
        "explanation": (
            "ML classifier detected OS memory pressure pattern with confidence {confidence:.2f} "
            "(Isolation Forest score: {if_score:.3f}). "
            "Host resource metrics match trained A6 signature. "
            "Review OS memory and CPU metrics for this ATM to confirm."
        ),
        "operation_impact": "ATM responsiveness is degraded and transactions may fail under host resource exhaustion.",
        "recommendation": (
            "Investigate host memory pressure on this ATM, "
            "review running processes for memory leaks, "
            "and consider restarting the ATM process or rebalancing to a higher-capacity host."
        ),
    },
    "A7": {
        "explanation": (
            "ML classifier detected malformed or out-of-order Kafka event pattern with confidence {confidence:.2f} "
            "(Isolation Forest score: {if_score:.3f}). "
            "Event sequencing and data quality features match trained A7 signature. "
            "Review Kafka partition ordering and Prometheus schema for this ATM."
        ),
        "operation_impact": "Monitoring accuracy is reduced, which may hide real operational issues or generate misleading diagnostics.",
        "recommendation": (
            "Validate event schema compliance, inspect Kafka partition ordering, "
            "and correct any malformed metric ingestion before relying on analysis."
        ),
    },
}


def _build_classifier_description(A_code, atm_id, confidence, if_score):
    """Return (explanation, operation_impact, recommendation) for classifier-detected anomalies."""
    tpl = _CLASSIFIER_DESCRIPTIONS.get(A_code)
    if not tpl:
        return (
            f"ML classifier detected {A_code} pattern with confidence {confidence:.2f} "
            f"(Isolation Forest score: {if_score:.3f}).",
            "Impact requires investigation.",
            "Review telemetry for this ATM to confirm the anomaly.",
        )
    return (
        tpl["explanation"].format(confidence=confidence, if_score=if_score),
        tpl["operation_impact"],
        tpl["recommendation"],
    )


def _to_datetime(value):
    """Normalise DB timestamp values to datetime.

    Supports psycopg2-returned datetime objects and legacy ISO string values.
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"Unsupported datetime value: {type(value)!r}")

def rank_algorithm(anomalies):

    '''
    these are the other key analysis i could think of that would help (I discarded previous ones, don't think we need them)
    1) ranked critical issue that needs to be resolved
    2) list of atm's that got operations affected

    How i would approah this
    1) i would have an algorithm to rank critical issues based on this factors(atm-anomaly frequency, operation_affected_gravity, severity breakdown,
     is_transaction_ip)
    2) operation_affected_gravity ranking: A1 - A4 - A3 - A2 - A6 - A5 - A7 
    3) send all unique atm-ids for the list of atm's that got affected
    '''

    '''
    ranked anomaly would contain all the normal fields and i have added an issue score and atm score which is basically for the frontend to use to rank
    the issues in an atm, so like the overall system ranked by atm's(you can put the score beside, also put the frequency of issues/anomalies), 
    then when you click view it now shows all the anomalies ranked. I have ranked the anomalies by putting atms with higher frequency at top 
    rank because i feel an atm with huge anomalies is worse than 1 system with critical anomaly.
    for the frontend, addie would give you the anomaly in the ranked order so as you receive it you want to use it like a fifo setup.
    addie you should probably not change the order, just receive the ranked anomaly(main passes the args to you already) and then add those fields, 
    don't tweak the order.
    '''
    
    # get the atm anomaly frequency(this gives us the frequecy of anomaly each atm has)
    # atm_counts = {}
    # for a in anomalies:
    #     aid = a['atm_id']
    #     atm_counts[aid] = atm_counts.get(aid, 0) + 1

    # implement the operation affected gravity mapping
    operation_ranking = {'A1': 7, 'A4': 6, 'A3': 5, 'A2': 4, 'A6': 3, 'A5': 2, 'A7': 1}
    
    # severity breakdown mapping
    severity_map = {"CRITICAL": 3, "HIGH": 2, "MAJOR":1, "WARNING": 0}

    # transaction in progress mapping
    transaction_map = {'is_transaction_t': 1, 'is_transaction_f': 0}

    combined_weights = {}
    reference_time = get_reference_now(anomalies)

    # to improve performance, i would create kv pair of anomaly so i can get a better search time
    # anomaly_map = {}
    counter_id = 0
    atm_tracker = {}

    # combine weights to get the total weight for ranking
    for a in anomalies:
        counter_id += 1
        
        #time map
        time_score = get_age_score(a.get('detected_at'), reference_time)

        # get score without frequency to rank anomalies in atm
        inner_score = (
                        operation_ranking.get(a['anomaly_type'], 0) +
                        severity_map.get(a['severity'], 0) +
                        (transaction_map.get('is_transaction_t', 0) if a['transaction_id'] else transaction_map.get('is_transaction_f', 0))+
                        time_score
                    )
        
        #just did a little testing with the weight, the weight currently makes a little difference which i think is fine since we need balance
        # print(inner_score - time_score)

        
        # rank anomaly by score
        a['issue_score'] = inner_score
        combined_weights[counter_id] = inner_score
        atm_tracker[counter_id] = a
        # calculate score with frequency to rank atm 
        # total_contribution = inner_score + atm_counts.get(unique_id, 0)
        # combined_weights[unique_id] = combined_weights.get(unique_id, 0) + total_contribution
        
        #list of all issues in atm
        # if unique_id not in anomaly_map:
        #     anomaly_map[unique_id] = []
        # anomaly_map[unique_id].append(a)

    # get ranked atms from critical to less critical
    ranked_dict = sorted(combined_weights.items(), key = lambda x: x[1], reverse = True)

    # rank the anomalies
    ranked_anomaly = []
    
    for id,_ in ranked_dict:
        ranked_anomaly.append(atm_tracker.get(id))        

        # sort the atm issues
        # atm_issues.sort(key = lambda x: x['issue_score'], reverse = True )

        #rank the atm issues and append it in order
        # for issues in atm_issues:
        #     issues['atm_score'] = total_score
        #     ranked_anomaly.append(issues)

    # unique affected atms
    # affected_atms = set(a['atm_id'] for a in anomalies)

    return ranked_anomaly

# this would get the automated static time by doing max detected at plus 2 days, okay correction: it just the max detected at time, no 2 days
def get_reference_now(anomalies):
    max_dt = None

    for a in anomalies:

        dt = _to_datetime(a["detected_at"])

        if max_dt is None or dt > max_dt:
            max_dt = dt

    #just use current time as max, if we are not able to get the max
    if max_dt is None:
        return datetime.now().astimezone()

    return max_dt


#create time weight(Instead of weighting time i think a conditional weight approach would make more sense)
def get_age_score(detected_at, reference_time):
    dt = _to_datetime(detected_at)

    '''
    get the current date and subtract it to get the hour difference (wait on second thought use a static date,
    because i want to cap it at 48 hours to balance it)
    '''
    # now = datetime.now(timezone.utc)

    '''
    using static data (maybe 2026 4 of, okay now that i think about it i might want automated static time instead, 
    detected at looks to recent, i suspect the system regenrates new timestamp every run) 
    '''
    # reference_now = datetime.fromisoformat("2026-04-01T12:00:00+00:00")
    
    '''
    calculate total hours (2 days - 48 hours) 
    (reference time is the 2 days after max detected at in anomalie set)
    (okay, after final run i think ref time is best to be max detected at time so it gets more balanced)
    '''
    age_hours = (reference_time - dt).total_seconds() / 3600
    
    #create conditional mapping for total age
    if age_hours >= 48:
        return 3
    elif age_hours >= 24:
        return 2
    elif age_hours >= 6:
        return 1
    else:
        return 0


# A1 detailed analysis(recommended fix, operation impact, root cause)
def A1(atm_id, error_seen, max_timeout, kafka_offline, terminal_timeout):

    # the anomalie explanation in details
    explanation = (
                    f"{atm_id} experienced a network timeout cascade. "
                    f"ATM application logs show a NETWORK_DISCONNECT event"
                    f"{' with ERR-0040' if error_seen else ''}, "
                    f"followed by a TIMEOUT"
                    f"{f' at {max_timeout}ms' if max_timeout else ''}. "
                    f"{'Kafka telemetry marked the ATM Offline and reported HOST_UNAVAILABLE. ' if kafka_offline else ''}"
                    f"{'Terminal handler logs also recorded NETWORK_TIMEOUT, confirming a cross-source network failure.' if terminal_timeout else ''}"
                  )


    # this would let client know if it an anomalie that would disrupt operations
    operational_impact = "ATM unavailable for customer transactions due to network connectivity failure."

    # recommended fix for anomalie
    recommendation = (
                        "Investigate the network link between the ATM and terminal handler, "
                        "validate backend is reachable, and restore connections before returning the ATM to service."
                      )

    return explanation, operational_impact, recommendation
    
# A2 detailed analysis(recommended fix, operation impact, root cause)
def A2(atm_id,low_count, empty_count, out_of_service, dispense_error, zero_tps):

    # the anomalie explanation in details
    explanation = (
                    f"{atm_id} showed a cash depletion sequence in hardware telemetry, "
                    f"with {low_count} CASSETTE_LOW event followed by {empty_count} CASSETTE_EMPTY event. "
                    f"{'Kafka telemetry also showed the ATM as Out of Service. ' if out_of_service else ''}"
                    f"{'Transaction metrics dropped to zero, indicating cash dispensing was no longer possible. ' if zero_tps else ''}"
                    f"{'A cash dispense error was also observed in correlated telemetry. ' if dispense_error else ''}"
                    "This indicates the ATM exhausted available cash cassettes."
                  )
    
    # this would let client know if it an anomalie that would disrupt operations
    operational_impact = "ATM cannot complete cash withdrawal operations and may be unavailable to customers at this location."
    
    # recommended fix for anomalie
    recommendation =  "Dispatch cash replenishment team, inspect cassette state, and keep the ATM out of service until cash is available."

    return explanation, operational_impact, recommendation

# A3 detailed analysis(recommended fix, operation impact, root cause)
def A3(mem_start, mem_end, gc_start, gc_end, high_cpu, oom_seen):

  # the anomalie explanation in details
    explanation =  (
                    f"Terminal handler memory usage increased from {mem_start:.0f} to {mem_end:.0f} bytes over the analysis window, "
                    f"while GC pause cumulative rose from {gc_start:.2f}s to {gc_end:.2f}s. "
                    f"{'CPU usage also rose sharply, indicating GC thrashing. ' if high_cpu else ''}"
                    f"{'A FATAL OutOfMemoryError was recorded in handler logs, confirming heap exhaustion.' if oom_seen else ''}"
                   )
    
    # this would let client know if it an anomalie that would disrupt operations
    operational_impact = "Backend transaction processing is unstable and at risk of service interruption across affected ATM flows."

    # recommended fix for anomalie
    recommendation =  "Inspect JVM heap growth, review memory allocation behaviour, observe garbage collection thoroughly, and restart the affected service if it required."

    return explanation, operational_impact, recommendation

# A4 detailed analysis(recommended fix, operation impact, root cause)
def A4(max_restart, fatal_count, startup_count):

    # the anomalie explanation in details
    explanation = (
                    f"Container restart telemetry showed repeated restart activity"
                    f"{f' up to {max_restart:.0f} restart' if max_restart is not None else ''}. "
                    f"Handler logs recorded {startup_count} STARTUP event"
                    f"{f' and {fatal_count} fatal failure' if fatal_count else ''}, "
                    "indicating the service repeatedly crashed and restarted within a short window."
                  )
    
    # this would let client know if it an anomalie that would disrupt operations
    operational_impact =" Service would be unstable which may interrupt or delay transaction handling across multiple ATM sessions."

    # recommended fix for anomalie
    recommendation = "Investigate the crash source, validate memory and container health, and make the service stable before returning it to normal traffic."

    return explanation, operational_impact, recommendation

# A5 detailed analysis(recommended fix, operation impact, root cause)
def A5(atm_id, max_rt, min_success, max_failures, timeout_seen):  
    # the anomalie explanation in details
    explanation = (
                    f"{atm_id} experienced a response-time spike, with latency rising to {max_rt:.0f}ms. "
                    f"{f'Transaction success rate fell to {min_success:.0f}%. ' if min_success is not None else ''}"
                    f"{f'Failure count increased to {max_failures:.0f}. ' if max_failures is not None else ''}"
                    f"{'ATM application logs also recorded a TIMEOUT with ERR-0012, confirming transaction degraded.' if timeout_seen else ''}"
                  )
    
    # this would let client know if it an anomalie that would disrupt operations
    operational_impact = " Customers may experience slow responses, failed transactions, and degraded ATM service quality."

    # recommended fix for anomalie
    recommendation = "Investigate latency, review host/network responsiveness, and monitor whether response time continues to rise toward timeout conditions."

    return explanation, operational_impact, recommendation

# A6 detailed analysis(recommended fix, operation impact, root cause)
def A6(atm_id, mem_start, mem_max, cpu_max, net_error_max, timeout_seen):

    # the anomalie explanation in details
    explanation = (
                    f"{atm_id} showed increasing host resource pressure, with memory usage rising from {mem_start:.2f}% to {mem_max:.2f}%"
                    f"{f' and CPU reaching {cpu_max:.2f}%' if cpu_max is not None else ''}. "
                    f"{f'Network errors also rose to {net_error_max:.0f}. ' if net_error_max is not None else ''}"
                    f"{'ATM application logs recorded a TIMEOUT with memory-pressure indicators such as ThreadAbortException.' if timeout_seen else ''}"
                )
    # this would let client know if it an anomalie that would disrupt operations
    operational_impact = "ATM responsiveness is degraded and transactions may fail under host resource exhaustion."

    # recommended fix for anomalie
    recommendation ="Investigate host memory pressure, review CPU and network health, and restart or rebalance the affected ATM process if resource contention persists."

    return explanation, operational_impact, recommendation

# A7 detailed analysis(recommended fix, operation impact, root cause)
def A7(atm_id,  missing_field_count, malformed_metric, ooo):

    # the anomalie explanation in details
    explanation = (
                    f"Malformed event ingestion was detected for {atm_id or 'the monitored stream'}, including "
                    f"{missing_field_count} event with required fields missing"
                    f"{' and out-of-order Kafka sequencing' if ooo else ''}"
                    f"{' as well as non-numeric metric values in Prometheus data' if malformed_metric else ''}. "
                    "This indicates data-quality issues in the ingestion or event pipeline."
                  )
    
    # this would let client know if it an anomalie that would disrupt operations
    operational_impact = "Monitoring accuracy is reduced, which may hide real operational issues or generate misleading diagnostics."

    # recommended fix for anomalie
    recommendation =  "Validate if schema design is followed, inspect event ordering in the Kafka pipeline, and correct malformed metric ingestion before relying analysis."

    return explanation, operational_impact, recommendation

def time_window(endtime_arg,time_delta):

    # convert to numeric so i can subtract to get estimated start time
    time_num = _to_datetime(endtime_arg)

    start_time_num = time_num - timedelta(minutes = time_delta)

    end_time = time_num.strftime('%Y-%m-%d %H:%M:%S')
    # convert back to string
    start_time = start_time_num.strftime('%Y-%m-%d %H:%M:%S')
    
    return start_time, end_time

'''
I have to delete the queries and field logic since i need too deliver the code quickly to the frontend, 
most of those fields don't exist so i just have to go with what evidence gives even if some key fields might be missing
'''
def build_detailed_table(anomalies):
    detailed_rows = []
    
    for a in anomalies:
        
        A_code = a['anomaly_type']
        atm_id = a.get('atm_id')
        raw = a.get("explanation")
        
        # Safely parse explanation JSON with fallback to empty dict
        try:
            exp = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, TypeError):
            exp = {}

        if A_code == "A1":

            end_time_arg = a['detected_at']         

             # get start time and endtime(i would use 10 minutes as my estimated time delta for A1)
            start_time, end_time = time_window(end_time_arg, 10)
            
            #explanation.json so i can quickly scan keys i need:
            # '{"network_disconnect": true, "error_code_correct": true, "timeout": true, "kafka_offline": true, "kafka_host_unavailable": true, "terminal_timeout": true, "last_ts": "2026-03-30T07:59:00+00:00"}

            # checklist
            error_seen, max_timeout, kafka_offline, terminal_timeout = (False, 0, False, False) 

            # use explanation to get keys 
            error_seen = exp.get('error_code_correct', False)
            max_timeout = 30000 if exp.get('timeout') else max_timeout
            kafka_offline = exp.get("kafka_offline", False)
            terminal_timeout = exp.get("terminal_timeout", False)

            explanation, operation_impact, recommendation = A1(atm_id, error_seen, max_timeout, kafka_offline, terminal_timeout)

            detailed_rows.append({
                "id": a.get('id'),
                "ATM_ID": atm_id,
                "Anomaly": A_code,
                "Severity": a['severity'],
                "Score": a['issue_score'],
                "Event_Time": f"{start_time} - {end_time}",
                "Title": a['title'],
                "root_cause": explanation,
                "operations": operation_impact,
                "Recommended_Action": recommendation,
                "recommended_action": a.get("recommended_action") or recommendation,
                "model_confidence_score": a.get("model_confidence_score"),
                "sources_involved": a.get("sources_involved") or [],
                "detection_source": exp.get("source") if isinstance(exp, dict) else None,
            })

        elif A_code == "A2":
            
            end_time_arg = a['detected_at']

            # get start time and endtime (i would use 60 minutes as my estimated time delta for A2(it seems like a long process for it to occur))
            start_time, end_time = time_window(end_time_arg, 60)

            #explanation.json so i can quickly scan keys i need:
            #{"low": 2, "empty": 2, "kafka_oos": true, "kafka_dispense_error": true, "kafka_trtps_zero": true, "last_ts": "2026-03-30T07:59:00+00:00"}
            
            # checklist
            low_count, empty_count, out_of_service, dispense_error, zero_tps = (0, 0, False, False, False) 
            
            # use explanation to get keys 
            low_count = exp.get('low', 0)
            empty_count = exp.get('empty', 0) 
            out_of_service = exp.get("kafka_oos", False)
            dispense_error = exp.get("kafka_dispense_error", False)
            zero_tps = exp.get("kafka_trtps_zero", False)

            explanation, operation_impact, recommendation = A2(atm_id, low_count, empty_count, out_of_service, dispense_error, zero_tps)

            detailed_rows.append({
                "id": a.get('id'),
                "ATM_ID": atm_id,
                "Anomaly": A_code,
                "Severity": a['severity'],
                "Score": a['issue_score'],
                "Event_Time": f"{start_time} - {end_time}",
                "Title": a['title'],
                "root_cause": explanation,
                "operations": operation_impact,
                "Recommended_Action": recommendation,
                "recommended_action": a.get("recommended_action") or recommendation,
                "model_confidence_score": a.get("model_confidence_score"),
                "sources_involved": a.get("sources_involved") or [],
                "detection_source": exp.get("source") if isinstance(exp, dict) else None,
            })

        elif A_code == "A3":

            end_time_arg = a['detected_at']

           
            # get start time and endtime (i would use 100 minutes as my estimated time delta for A3(just memory usage takes 90 minutes, so i think the rest would be in 10)
            start_time, end_time = time_window(end_time_arg, 100)

            #explanation.json so i can quickly scan keys i need:
            #'{"pod": "terminal-handler-pod-0", "points": [300000114.0, 299999099.0, 300000870.0, 299999128.0, 1040000000.0], "rel_increase": 2.4666749982422456, "frac_increase": 0.55}'
            # ML_ENSEMBLE format: '{"confidence": 0.99, "source": "CLASSIFIER", "window_seconds": 7200, "if_score": -0.706}'

            # checklist
            mem_start, mem_end, gc_start, gc_end, high_cpu, oom_seen = (0, 0, 0, 0, False, False)
            source = exp.get("source", "UNKNOWN")

            if source in ("ML_ENSEMBLE", "CLASSIFIER"):
                if_score = exp.get("if_score", 0)
                confidence = exp.get("confidence", 0)
                explanation, operation_impact, recommendation = _build_classifier_description(A_code, atm_id, confidence, if_score)
            else:
                points = exp.get("points", [])
                
                #gets first and last point
                mem_start = points[0] if points else mem_start
                mem_end =  points[-1] if points else mem_end

                #no gc start in explanation so we have to skip that metric

                high_cpu = True if (exp.get("frac_increase") or 0) >= 0.5 else high_cpu
                oom_seen = exp.get("oom_seen", False) or exp.get("xgb_predicted") == "OutOfMemoryError"

                explanation, operation_impact, recommendation = A3(mem_start, mem_end, gc_start, gc_end, high_cpu, oom_seen)

            detailed_rows.append({
                "id": a.get('id'),
                "ATM_ID": atm_id,
                "Anomaly": A_code,
                "Severity": a['severity'],
                "Score": a['issue_score'],
                "Event_Time": f"{start_time} - {end_time}",
                "Title": a['title'],
                "root_cause": explanation,
                "operations": operation_impact,
                "Recommended_Action": recommendation,
                "recommended_action": a.get("recommended_action") or recommendation,
                "model_confidence_score": a.get("model_confidence_score"),
                "sources_involved": a.get("sources_involved") or [],
                "detection_source": exp.get("source") if isinstance(exp, dict) else None,
            })


        elif A_code == "A4":

            end_time_arg = a['detected_at']

            # get start time and endtime(i would use 5 minutes as my estimated time delta for A4(i think the guide specifically says under 5 minutes so this is more factual than estimate))
            start_time, end_time = time_window(end_time_arg, 5)
            
            #explanation.json so i can quickly scan keys i need:
            #'{"gcp_restarts": [{"ts": "2026-03-29T09:32:00+00:00", "count": 1.0} {"ts": "2026-03-29T09:34:00+00:00", "count": 2.0}], "total_startups": 3, "total_fatals": 3}'
            # ML_ENSEMBLE format: '{"confidence": 0.82, "source": "CLASSIFIER", "window_seconds": 7200, "if_score": -0.71}'

            # checklist
            max_restart, fatal_count, startup_count = (0, 0, 0)
            source = exp.get("source", "UNKNOWN")

            if source in ("ML_ENSEMBLE", "CLASSIFIER"):
                if_score = exp.get("if_score", 0)
                confidence = exp.get("confidence", 0)
                explanation, operation_impact, recommendation = _build_classifier_description(A_code, atm_id, confidence, if_score)
            else:
                # get max count
                restart = exp.get("gcp_restarts", [])
                for r in restart:
                    count = r.get("count", 0)
                    if count > max_restart:
                        max_restart = count
                
                fatal_count = exp.get('total_fatals', 0)
                startup_count = exp.get('total_startups', 0)

                explanation, operation_impact, recommendation = A4(max_restart, fatal_count, startup_count)

            detailed_rows.append({
                "id": a.get('id'),
                "ATM_ID": atm_id,
                "Anomaly": A_code,
                "Severity": a['severity'],
                "Score": a['issue_score'],
                "Event_Time": f"{start_time} - {end_time}",
                "Title": a['title'],
                "root_cause": explanation,
                "operations": operation_impact,
                "Recommended_Action": recommendation,
                "recommended_action": a.get("recommended_action") or recommendation,
                "model_confidence_score": a.get("model_confidence_score"),
                "sources_involved": a.get("sources_involved") or [],
                "detection_source": exp.get("source") if isinstance(exp, dict) else None,
            })

        elif A_code == "A5":

            end_time_arg = a['detected_at']

            # get start time and endtime (i would use 10 minutes as my estimated time delta for A5)
            start_time, end_time = time_window(end_time_arg, 10)

            #explanation.json so i can quickly scan keys i need:
            #'{"spikes": [{"ts": "2026-03-29T09:30:00+00:00", "rt": 3200.0, "sr": 72.0, "fc": 8.0}, {"ts": "2026-03-29T09:31:00+00:00", "rt": 30000.0, "sr": 50.0, "fc": 14.0}], "timeouts": [{"ts": "2026-03-29T09:30:00+00:00", "txn": "txn-d95dbe59-dfe"}, {"ts": "2026-03-29T09:31:00+00:00", "txn": "txn-d95dbe59-dfe"}]}', 
            # ML_ENSEMBLE format: '{"confidence": 0.95, "source": "CLASSIFIER", "window_seconds": 7200, "if_score": -0.755}'

            # checklist
            max_rt5, min_success, max_failures, timeout_seen = (0, None, 0, False)
            source = exp.get("source", "UNKNOWN")

            if source in ("ML_ENSEMBLE", "CLASSIFIER"):
                if_score = exp.get("if_score", 0)
                confidence = exp.get("confidence", 0)
                explanation, operation_impact, recommendation = _build_classifier_description(A_code, atm_id, confidence, if_score)
            else:
                #get max response time
                spikes = exp.get("spikes", [])
                for s in spikes:
                    rt = s.get("rt") or 0
                    if rt > max_rt5:
                        max_rt5 = rt
                        
                #get min success
                for s in spikes:
                    sr = s.get("sr")
                    if sr is not None and (min_success is None or sr < min_success):
                        min_success = sr
                           
                # get max failure
                for s in spikes:
                    fc = s.get("fc")
                    if fc is not None and fc > max_failures:
                        max_failures = fc

                timeout = exp.get("timeouts")
                if timeout:
                    timeout_seen = True

                explanation, operation_impact, recommendation = A5(atm_id, max_rt5, min_success, max_failures, timeout_seen)
  
            
            detailed_rows.append({
                "id": a.get('id'),
                "ATM_ID": atm_id,
                "Anomaly": A_code,
                "Severity": a['severity'],
                "Score": a['issue_score'],
                "Event_Time": f"{start_time} - {end_time}",
                "Title": a['title'],
                "root_cause": explanation,
                "operations": operation_impact,
                "Recommended_Action": recommendation,
                "recommended_action": a.get("recommended_action") or recommendation,
                "model_confidence_score": a.get("model_confidence_score"),
                "sources_involved": a.get("sources_involved") or [],
                "detection_source": exp.get("source") if isinstance(exp, dict) else None,
            })
        
        elif A_code == "A6":

            end_time_arg = a['detected_at']

            # get start time and endtime (i would use 120 minutes as my estimated time delta for A6(it seems like a long process for it to occur))
            start_time, end_time= time_window(end_time_arg, 120)

            #explanation.json so i can quickly scan keys i need:
            #'{"memory_samples": [10.06, 24.63, 19.09, 10.13, 35.13], "timeout": {"ts": "2026-03-29T09:45:00+00:00", "error_detail": "ThreadAbortException: memory pressure", "error_code": "ERR-MEM"}}'
            # ML_ENSEMBLE format: '{"confidence": 0.96, "source": "CLASSIFIER", "window_seconds": 7200, "if_score": -0.688}'

            # checklist
            mem_start, mem_max, cpu_max, net_error_max, timeout_seen = (0, 0, 0, 0, False)
            source = exp.get("source", "UNKNOWN")

            if source in ("ML_ENSEMBLE", "CLASSIFIER"):
                if_score = exp.get("if_score", 0)
                confidence = exp.get("confidence", 0)
                explanation, operation_impact, recommendation = _build_classifier_description(A_code, atm_id, confidence, if_score)
            else:
                #get mem start
                spikes = exp.get("memory_samples", [])

                mem_start = spikes[0] if spikes else mem_start

                for s in spikes:
                    if s > mem_max:
                        mem_max = s
                
                timeout = exp.get("timeout", {})
                error = timeout.get("error_detail", "")
                if error == "ThreadAbortException: memory pressure":        
                    timeout_seen = True        

                explanation, operation_impact, recommendation = A6(atm_id, mem_start, mem_max, cpu_max, net_error_max, timeout_seen)

            detailed_rows.append({
                "id": a.get('id'),
                "ATM_ID": atm_id,
                "Anomaly": A_code,
                "Severity": a['severity'],
                "Score": a['issue_score'],
                "Event_Time": f"{start_time} - {end_time}",
                "Title": a['title'],
                "root_cause": explanation,
                "operations": operation_impact,
                "Recommended_Action": recommendation,
                "recommended_action": a.get("recommended_action") or recommendation,
                "model_confidence_score": a.get("model_confidence_score"),
                "sources_involved": a.get("sources_involved") or [],
                "detection_source": exp.get("source") if isinstance(exp, dict) else None,
            })


        elif A_code == "A7":
             
            end_time_arg = a['detected_at']

            # get start time and endtime (i would use 10 minutes as my estimated time delta for A7)
            start_time, end_time = time_window(end_time_arg, 10)
            
            #explanation.json so i can quickly scan keys i need:
            #'{"prom_err_id": 2, "kafka_err_id": 1, "prom_ts": "2026-03-29T15:18:57.814751+00:00", "kafka_ts": "2026-03-29T15:18:57.667783+00:00"}'
            # ML_ENSEMBLE format: '{"confidence": 0.73, "source": "CLASSIFIER", "window_seconds": 7200, "if_score": -0.699}'
            
            # checklist
            missing_field_count, malformed_metric, ooo  = (0, False, False)
            source = exp.get("source", "UNKNOWN")

            if source in ("ML_ENSEMBLE", "CLASSIFIER"):
                if_score = exp.get("if_score", 0)
                confidence = exp.get("confidence", 0)
                explanation, operation_impact, recommendation = _build_classifier_description(A_code, atm_id, confidence, if_score)
            else:
                if exp.get("prom_err_id"):
                    missing_field_count += 1
                    malformed_metric = True

                if exp.get("kafka_err_id"):
                    missing_field_count += 1
                    ooo = True
                
                explanation, operation_impact, recommendation = A7(atm_id,  missing_field_count, malformed_metric, ooo)

            detailed_rows.append({
                "id": a.get('id'),
                "ATM_ID": atm_id,
                "Anomaly": A_code,
                "Severity": a['severity'],
                "Score": a['issue_score'],
                "Event_Time": f"{start_time} - {end_time}",
                "Title": a['title'],
                "root_cause": explanation,
                "operations": operation_impact,
                "Recommended_Action": recommendation,
                "recommended_action": a.get("recommended_action") or recommendation,
                "model_confidence_score": a.get("model_confidence_score"),
                "sources_involved": a.get("sources_involved") or [],
                "detection_source": exp.get("source") if isinstance(exp, dict) else None,
            })

        elif A_code == "UNKNOWN":

            end_time_arg = a['detected_at']

            start_time, end_time = time_window(end_time_arg, 10)

            source = exp.get("source", "UNKNOWN")
            if source == "ZSCORE":
                max_z = exp.get("max_z_score", 0)
                n_dev = exp.get("n_features_deviating", 0)
                explanation = (
                    f"Statistical deviation detected: {n_dev} features exceeded 3σ threshold "
                    f"(max z-score: {max_z:.2f}). Pattern does not match any known anomaly type."
                )
            else:
                if_score = exp.get("if_score", 0)
                xgb_pred = exp.get("xgb_predicted", "N/A")
                xgb_conf = exp.get("xgb_confidence", 0)
                explanation = (
                    f"Isolation Forest flagged anomalous behavior (score: {if_score:.3f}), "
                    f"but XGBoost classified as {xgb_pred} (confidence: {xgb_conf:.2f}). "
                    f"Pattern is novel and does not match trained A1–A7 signatures."
                )

            operation_impact = "System behavior is atypical; impact depends on underlying cause which requires investigation."
            recommendation = (
                "Review telemetry across all sources (ATM app, Kafka, Prometheus, GCP) for this time window. "
                "Check for recent deployments, config changes, or traffic anomalies. "
                "If pattern recurs, consider adding it to the training dataset."
            )

            detailed_rows.append({
                "id": a.get('id'),
                "ATM_ID": atm_id,
                "Anomaly": A_code,
                "Severity": a['severity'],
                "Score": a['issue_score'],
                "Event_Time": f"{start_time} - {end_time}",
                "Title": a['title'],
                "root_cause": explanation,
                "operations": operation_impact,
                "Recommended_Action": recommendation,
                "recommended_action": a.get("recommended_action") or recommendation,
                "model_confidence_score": a.get("model_confidence_score"),
                "sources_involved": a.get("sources_involved") or [],
                "detection_source": exp.get("source") if isinstance(exp, dict) else None,
            })

    return detailed_rows


# create connection
def query(sql: str, params: tuple = ()):  # -> List[Dict[str, Any]]
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    finally:
        try:
            release_conn(conn)
        except Exception:
            pass


# run analysis
def main():
    sql_query = "SELECT * FROM anomalies"
    anomalies = query(sql_query)
   
   
    ranked_anomaly= rank_algorithm(anomalies)
    data = build_detailed_table(ranked_anomaly)
    
    return data 
