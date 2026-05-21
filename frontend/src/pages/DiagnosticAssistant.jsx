import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getRAGStats, getRAGHistory } from "../api/api";
import { useRAG } from "../providers/useRAG";
import { Card, CardContent } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import { Skeleton } from "../components/ui/skeleton";
import {
  Send, Plus, MessageCircle, History, Sparkles, ChevronDown, ChevronUp,
  Brain, Wrench, AlertTriangle, Clock, CheckCircle, XCircle,
  AlertCircle, RefreshCw, Layers, Target, FileSearch,
} from "lucide-react";
import { formatUKDateTime } from "../lib/utils";

function TypingIndicator() {
  return (
    <div className="flex gap-1 items-center px-1">
      <span className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
      <span className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
      <span className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
    </div>
  );
}

function ConfidenceBreakdown({ uncertainty }) {
  const [expanded, setExpanded] = useState(false);
  const signals = [
    { key: "retrieval", label: "Retrieval", score: uncertainty.uncertainty_score, color: "bg-blue-500" },
    { key: "consistency", label: "Consistency", score: uncertainty.selfConsistencyScore, color: "bg-violet-500" },
    { key: "verbalized", label: "Verbalized", score: uncertainty.verbalizedConfidence, color: "bg-amber-500" },
    { key: "grounding", label: "Grounding", score: uncertainty.groundingScore, color: "bg-emerald-500" },
  ].filter(s => s.score != null);

  return (
    <div className="mt-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <Layers className="w-3 h-3" />
        Confidence breakdown
        {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>
      {expanded && (
        <div className="mt-2 space-y-1.5 p-2 rounded-md bg-secondary/50 border border-border">
          {signals.map((s) => (
            <div key={s.key} className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground w-20 shrink-0">{s.label}</span>
              <div className="flex-1 h-2 rounded-full bg-secondary">
                <div
                  className={`h-full rounded-full transition-all ${s.color}`}
                  style={{ width: `${(s.score * 100).toFixed(0)}%` }}
                />
              </div>
              <span className="text-xs font-mono w-10 text-right">{(s.score * 100).toFixed(0)}%</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AgenticBadges({ uncertainty }) {
  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {uncertainty.crossEncoderUsed && (
        <Badge variant="outline" className="text-[10px] border-blue-500/30 text-blue-600 bg-blue-500/5">
          <Target className="w-2.5 h-2.5 mr-1" />
          Reranked
        </Badge>
      )}
      {uncertainty.wasRevised && (
        <Badge variant="outline" className="text-[10px] border-amber-500/30 text-amber-600 bg-amber-500/5">
          <RefreshCw className="w-2.5 h-2.5 mr-1" />
          Revised after critique
        </Badge>
      )}
      {!uncertainty.wasRevised && uncertainty.modelUsed !== "cache" && uncertainty.modelUsed !== "db_stats" && (
        <Badge variant="outline" className="text-[10px] border-emerald-500/30 text-emerald-600 bg-emerald-500/5">
          <CheckCircle className="w-2.5 h-2.5 mr-1" />
          Self-reviewed
        </Badge>
      )}
      {uncertainty.groundingScore != null && (
        <Badge variant="outline" className={`text-[10px] ${
          uncertainty.groundingScore >= 0.8
            ? "border-emerald-500/30 text-emerald-600 bg-emerald-500/5"
            : uncertainty.groundingScore >= 0.5
            ? "border-amber-500/30 text-amber-600 bg-amber-500/5"
            : "border-red-500/30 text-red-600 bg-red-500/5"
        }`}>
          <FileSearch className="w-2.5 h-2.5 mr-1" />
          Grounding: {(uncertainty.groundingScore * 100).toFixed(0)}%
        </Badge>
      )}
    </div>
  );
}

function CritiqueSection({ critiqueText }) {
  const [expanded, setExpanded] = useState(false);
  if (!critiqueText) return null;
  return (
    <div className="mt-2 pt-2 border-t border-border/50">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <AlertCircle className="w-3 h-3" />
        {expanded ? "Hide" : "Show"} critique
        {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>
      {expanded && (
        <div className="mt-1.5 text-xs p-2 rounded-md bg-red-500/5 border border-red-500/20 text-muted-foreground whitespace-pre-wrap">
          {critiqueText}
        </div>
      )}
    </div>
  );
}

function ConfidenceBadge({ level, score, uncertainty }) {
  const config = {
    HIGH: { color: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20", icon: CheckCircle },
    MEDIUM: { color: "bg-amber-500/10 text-amber-600 border-amber-500/20", icon: AlertCircle },
    LOW: { color: "bg-red-500/10 text-red-600 border-red-500/20", icon: XCircle },
  };
  const { color, icon: Icon } = config[level] || config.LOW;
  return (
    <div>
      <Badge variant="outline" className={`text-xs font-medium ${color}`}>
        <Icon className="w-3 h-3 mr-1" />
        {level} confidence
        {score !== undefined && <span className="ml-1 opacity-60">({(score * 100).toFixed(0)}%)</span>}
      </Badge>
      {uncertainty && <ConfidenceBreakdown uncertainty={uncertainty} />}
    </div>
  );
}

function SourceList({ sources }) {
  const [expanded, setExpanded] = useState(false);
  if (!sources || sources.length === 0) return null;
  return (
    <div className="mt-3 pt-3 border-t border-border">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        {sources.length} source{sources.length > 1 ? "s" : ""} used
      </button>
      {expanded && (
        <div className="mt-2 space-y-2">
          {sources.map((src, i) => (
            <div key={i} className="text-xs p-2 rounded-md bg-secondary/50 border border-border">
              <div className="flex items-center justify-between mb-1">
                <span className="font-medium text-foreground">{src.atm_id || "Unknown Entity"}</span>
                <span className="text-muted-foreground">{src.confidence_score ? `Confidence: ${(src.confidence_score * 100).toFixed(0)}%` : ""}</span>
              </div>
              <div className="text-muted-foreground mb-1">{src.timestamp ? formatUKDateTime(src.timestamp) : ""}</div>
              <div className="text-foreground/80 line-clamp-3 whitespace-pre-wrap">{src.text}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function HistoryItem({ query }) {
  const [expanded, setExpanded] = useState(false);
  const score = query.uncertainty_score ?? 0.5;
  const level = score >= 0.7 ? "HIGH" : score >= 0.4 ? "MEDIUM" : "LOW";
  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-3 text-left hover:bg-secondary/50 transition-colors"
      >
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{query.query_text}</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {formatUKDateTime(query.created_at)} • {level} confidence ({(score * 100).toFixed(0)}%)
          </p>
        </div>
        <div className="flex items-center gap-2 ml-3 shrink-0">
          <Badge variant="outline" className={`text-xs ${
            level === "HIGH" ? "text-emerald-600" :
            level === "MEDIUM" ? "text-amber-600" : "text-red-600"
          }`}>
            {level}
          </Badge>
          {expanded ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
        </div>
      </button>
      {expanded && (
        <div className="px-3 pb-3 border-t border-border">
          <div className="mt-3 text-sm text-muted-foreground whitespace-pre-wrap">{query.answer_text}</div>
        </div>
      )}
    </div>
  );
}

function DiagnosticAssistant() {
  const {
    messages,
    input, setInput,
    loading,
    activeTab, setActiveTab,
    submitQuery,
    handleNewChat,
  } = useRAG();

  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyPage, setHistoryPage] = useState(1);
  const [hasMoreHistory, setHasMoreHistory] = useState(true);
  const messagesEndRef = useRef(null);

  const fetchHistory = async (page) => {
    setHistoryLoading(true);
    try {
      const limit = 20;
      const offset = (page - 1) * limit;
      const data = await getRAGHistory(limit, offset);
      const queries = data.history || data.queries || data.data || [];
      if (page === 1) {
        setHistory(queries);
      } else {
        setHistory(prev => [...prev, ...queries]);
      }
      setHasMoreHistory(queries.length === limit);
    } catch (err) {
      console.error("Failed to fetch history:", err);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        await getRAGStats();
      } catch (err) {
        console.error("Failed to fetch stats:", err);
      }
    };
    fetchStats();
  }, []);

  useEffect(() => {
    if (activeTab === "history") {
      fetchHistory(1);
    }
  }, [activeTab, fetchHistory]);

  const handleSubmit = (e) => {
    e.preventDefault();
    submitQuery(input);
  };

  const exampleQueries = [
    { text: "What does anomaly type A1 mean?", icon: Brain },
    { text: "How do I fix a cash cassette empty error?", icon: Wrench },
    { text: "Show me recent network timeout issues", icon: AlertTriangle },
    { text: "What's causing high response times on ATM-GB-0001?", icon: Clock },
  ];

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <div className="flex items-center justify-between mb-4">
        <div className="flex gap-2">
          <Button variant={activeTab === "chat" ? "default" : "outline"} onClick={() => setActiveTab("chat")} className="gap-2">
            <MessageCircle className="w-4 h-4" /> Chat
          </Button>
          <Button variant={activeTab === "history" ? "default" : "outline"} onClick={() => setActiveTab("history")} className="gap-2">
            <History className="w-4 h-4" /> History
          </Button>
        </div>
        {activeTab === "chat" && (
          <Button variant="outline" onClick={handleNewChat} className="gap-2">
            <Plus className="w-4 h-4" /> New Chat
          </Button>
        )}
      </div>

      {activeTab === "chat" && (
        <div className="flex flex-col flex-1 min-h-0">
          <div className="flex-1 overflow-y-auto space-y-4 pr-2">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}
              >
                <div className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
                  msg.role === "user" ? "bg-primary text-primary-foreground" : "bg-gradient-to-br from-violet-500 to-indigo-600 text-white"
                }`}>
                  {msg.role === "user" ? (
                    <span className="text-xs font-medium">You</span>
                  ) : (
                    <Sparkles className="w-4 h-4" />
                  )}
                </div>
                <div className={`flex-1 max-w-[80%] p-4 rounded-2xl ${
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground rounded-tr-sm"
                    : "bg-card border border-border rounded-tl-sm shadow-sm"
                }`}>
                  <div className="text-sm leading-relaxed prose prose-sm dark:prose-invert max-w-none prose-headings:font-semibold prose-headings:mb-2 prose-p:mb-2 prose-ul:mb-2 prose-ol:mb-2 prose-li:mb-0.5 prose-code:bg-secondary prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-pre:bg-secondary prose-pre:p-3 prose-pre:rounded-lg prose-blockquote:border-l-2 prose-blockquote:border-primary/30 prose-blockquote:pl-3 prose-blockquote:text-muted-foreground prose-strong:font-semibold prose-a:text-primary prose-a:underline">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {msg.content}
                    </ReactMarkdown>
                  </div>
                  {msg.uncertainty && (
                    <div className="mt-2">
                      <ConfidenceBadge
                        level={msg.uncertainty.level}
                        score={msg.uncertainty.score}
                        uncertainty={msg.uncertainty}
                      />
                      <AgenticBadges uncertainty={msg.uncertainty} />
                    </div>
                  )}
                  {msg.critiqueText && <CritiqueSection critiqueText={msg.critiqueText} />}
                  <SourceList sources={msg.sources} />
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex gap-3">
                <div className="shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center">
                  <Sparkles className="w-4 h-4 text-white" />
                </div>
                <div className="p-4 rounded-2xl rounded-tl-sm bg-card border border-border shadow-sm">
                  <TypingIndicator />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {messages.length <= 1 && !loading && (
            <Card className="mt-4 border-dashed">
              <CardContent className="pt-6">
                <div className="flex items-center gap-2 mb-3">
                  <Sparkles className="w-4 h-4 text-violet-500" />
                  <h3 className="font-semibold">Try asking about</h3>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {exampleQueries.map((q, i) => (
                    <Button
                      key={i}
                      variant="outline"
                      size="sm"
                      onClick={() => setInput(q.text)}
                      className="justify-start gap-2 h-auto py-2.5 text-left hover:border-violet-500/50 hover:bg-violet-500/10 hover:text-violet-700 transition-all"
                    >
                      <q.icon className="w-3.5 h-3.5 shrink-0 text-muted-foreground" />
                      <span className="text-sm truncate">{q.text}</span>
                    </Button>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          <form onSubmit={handleSubmit} className="flex gap-2 mt-4 pt-4 border-t border-border">
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about ATM errors, anomalies, or troubleshooting..."
              disabled={loading}
              className="flex-1"
            />
            <Button type="submit" disabled={loading || !input.trim()} className="gap-2">
              <Send className="w-4 h-4" />
              Send
            </Button>
          </form>
        </div>
      )}

      {activeTab === "history" && (
        <div className="flex flex-col flex-1 min-h-0">
          {historyLoading && history.length === 0 ? (
            <div className="space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-16 rounded-lg" />
              ))}
            </div>
          ) : history.length === 0 ? (
            <Card>
              <CardContent className="p-6">
                <p className="text-muted-foreground text-center">No query history yet. Start a conversation in the Chat tab.</p>
              </CardContent>
            </Card>
          ) : (
            <>
              <div className="flex-1 overflow-y-auto space-y-3 pr-2">
                {history.map((query, i) => (
                  <HistoryItem key={query.id || i} query={query} />
                ))}
              </div>
              {hasMoreHistory && (
                <div className="mt-4 pt-4 border-t border-border">
                  <Button
                    variant="outline"
                    onClick={() => {
                      const nextPage = historyPage + 1;
                      setHistoryPage(nextPage);
                      fetchHistory(nextPage);
                    }}
                    className="w-full"
                  >
                    Load More
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default DiagnosticAssistant;
