import sqlite3
from typing import List, Dict

REQUIRED_FIELDS =['ATM_ID', 'Anomaly', 'Severity', 'Event_Time', 'Status', 'Technical_Explanation', 'operations','Recommended_Action']

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
    atm_counts = {}
    for a in anomalies:
        aid = a['atm_id']
        atm_counts[aid] = atm_counts.get(aid, 0) + 1

    # implement the operation affected gravity mapping
    operation_ranking = {'A1': 7, 'A4': 6, 'A3': 5, 'A2': 4, 'A6': 3, 'A5': 2, 'A7': 1}
    
    # severity breakdown mapping
    severity_map = {"CRITICAL": 2, "HIGH": 1, "WARNING": 0}

    # transaction in progress mapping
    transaction_map = {'is_trasaction_t': 1, 'is_transaction_f': 0}

    combined_weights = {}

    # to improve performance, i would create kv pair of anomaly so i can get a better search time
    anomaly_map = {}

    # combine weights to get the total weight for ranking
    for a in anomalies:
        unique_id = a['atm_id']

        # get score without frequency to rank anomalies in atm
        inner_score = (
                        operation_ranking.get(a['anomaly_code'], 0) +
                        severity_map.get(a['severity'], 0) +
                        (transaction_map.get('is_transaction_t', 0) if a['transaction_id'] else transaction_map.get('is_transaction_f', 0))
                    )
        
        # rank anomaly by score
        a['issue_score'] = inner_score
        
        # calculate score with frequency to rank atm 
        total_contribution = inner_score + atm_counts.get(unique_id, 0)
        combined_weights[unique_id] = combined_weights.get(unique_id, 0) + total_contribution
        
        #list of all issues in atm
        if unique_id not in anomaly_map:
            anomaly_map[unique_id] = []
        anomaly_map[unique_id].append(a)

    # get ranked atms from critical to less critical
    ranked_dict = sorted(combined_weights.items(), key = lambda x: x[1], reverse = True)

    # rank the anomalies
    ranked_anomaly = []
    
    for id, total_score in ranked_dict:
        atm_issues:List[Dict] = anomaly_map.get(id)

        # sort the atm issues
        atm_issues.sort(key = lambda x: x['issue_score'], reverse = True )

        #rank the atm issues and append it in order
        for issues in atm_issues:
            issues['atm_score'] = total_score
            ranked_anomaly.append(issues)

    # unique affected atms
    affected_atms = set(a['atm_id'] for a in anomalies)

    return ranked_anomaly, affected_atms


def build_detailed_table(anomalies):
    detailed_rows = []
    
    for a in anomalies:

        # explain the anomalie in details
        explanation = f"ATM {a['atm_id']} reported a Critical Cash Depletion. " \
                      f"sensor moved from LOW to EMPTY, triggering an Out of Service state."
        
        #I assume this would let them know if it an anomalie that would disrupt operations(get team input on this, i feel it would be a nice addon)
        operational_impact= " this ATM is currently unable to serve withdrawal transactions, which may impact customer availability at this location."

        # Give the recommended fix for a2 anomalie(expanding it we would actually need an automated way)
        recommendation = "IMMEDIATE: Dispatch cash replenishment team and mark ATM as temporarily out of service until resolved. Reset hardware sensors upon refill."
        
        # I think we can expand it to include time when the anomaly detectors are able to give sequence time
        
        #build rows so i can use it to create dashboard in excel
        detailed_rows.append({
            "ATM_ID": a['atm_id'],
            "Anomaly": a['anomaly_code'],
            "Severity": a['severity'],
            "Event_Time": a['start_time'],
            "Status": "CRITICAL",
            "Technical_Explanation": explanation,
            "operations": operational_impact,
            "Recommended_Action": recommendation
        })
        
    return detailed_rows

# query db to get the anomalie table fields
def query(DB_PATH: str, sql, params=()):
    """
    Executes a SQL query against the SQLite database and returns the results as a list of dictionaries.
    Args:
    - sql (str): The SQL query to execute.
    - params (tuple): Optional parameters to pass to the SQL query.
    Returns:
    - List[Dict]: A list of dictionaries representing the rows returned by the query.
    """
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(sql, params).fetchall()
    con.close()
    
    return [dict(r) for r in rows]

# run analysis
def main():
    DB_PATH = "../database/database.db"
    sql_query = "SELECT * FROM anomalies"
    anomalies = query(DB_PATH, sql_query)
   
    ranked_anomaly, affected_atms = rank_algorithm(anomalies)
    data = build_detailed_table(ranked_anomaly)
    
    return data, affected_atms
