import { ChevronLeft, ChevronRight } from "lucide-react";

const logs = [
  {
    id: 1,
    message:
      "Cash cassette 2 is empty. All cassettes exhausted. ATM transitioning to Out of...",
    timestamp: "2026-03-05T09:58:44.000Z",
  },
  {
    id: 2,
    message: "Cash cassette 1 is empty. ATM cannot dispense from cassette 1.",
    timestamp: "2026-03-05T09:45:10.000Z",
  },
  {
    id: 3,
    message:
      "Cash cassette 2 note count below warning threshold. Remaining: 31 notes.",
    timestamp: "2026-03-05T09:15:22.000Z",
  },
  {
    id: 4,
    message:
      "Cash cassette 1 note count below warning threshold. Remaining: 48 notes.",
    timestamp: "2026-03-05T09:00:00.000Z",
  },
];

function SectionBox({ children }) {
  return <div style={styles.sectionBox}>{children}</div>;
}

function ActionButton({ label }) {
  return <button style={styles.actionButton}>{label}</button>;
}

function LogCard({ message, timestamp }) {
  return (
    <div style={styles.logCard}>
      <div style={styles.logTextArea}>
        <p style={styles.logMessage}>{message}</p>
        <p style={styles.logTimestamp}>{timestamp}</p>
      </div>

      <div style={styles.logButtonArea}>
        <button style={styles.viewButton}>View</button>
      </div>
    </div>
  );
}

export default function AnomalyData() {
  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <h1 style={styles.title}>Cassette Empty</h1>

        <div style={styles.buttonGroup}>
          <ActionButton label="Mark as Important" />
          <ActionButton label="Mark as Complete" />
        </div>
      </div>

      <div style={styles.mainGrid}>
        <div>
          <SectionBox>
            <div style={styles.logoBox}>
              <span style={styles.logoText}>Logo Placeholder</span>
            </div>
          </SectionBox>

          <div style={styles.logsSectionSpacing}>
            <SectionBox>
              <h2 style={styles.sectionTitle}>Relevant Logs</h2>

              <div style={styles.logsList}>
                {logs.map((log) => (
                  <LogCard
                    key={log.id}
                    message={log.message}
                    timestamp={log.timestamp}
                  />
                ))}
              </div>

              <div style={styles.paginationWrap}>
                <div style={styles.pagination}>
                  <button style={styles.paginationButton}>
                    <ChevronLeft size={20} />
                  </button>
                  <div style={styles.paginationDivider} />
                  <button style={styles.paginationButton}>
                    <ChevronRight size={20} />
                  </button>
                </div>
              </div>
            </SectionBox>
          </div>
        </div>

        <div style={styles.rightColumn}>
          <SectionBox>
            <div style={styles.atmHeader}>
              <div>
                <h2 style={styles.boxHeadingUpper}>ATM Issue</h2>
                <p style={styles.boxText}>ATM ID: ATM-GB-0003</p>
                <p style={styles.boxText}>Status: Out of Service</p>
              </div>

              <div style={styles.infoCircle}>i</div>
            </div>
          </SectionBox>

          <SectionBox>
            <h2 style={styles.boxHeading}>Technical Explanation</h2>
            <p style={styles.boxParagraph}>
              The ATM is experiencing cassette depletion and delayed sensor
              responses, which prevents proper dispense confirmation. This
              results in transaction failures and timeout errors within the
              system.
            </p>
          </SectionBox>

          <SectionBox>
            <h2 style={styles.boxHeading}>Recommended Action</h2>
            <p style={styles.boxParagraph}>
              Refill cash cassettes immediately and inspect sensor
              responsiveness. Perform diagnostics on the dispensing module and
              verify system communication stability.
            </p>
          </SectionBox>
        </div>
      </div>
    </div>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    background: "#f4f4f4",
    padding: "48px",
    color: "#000",
    fontFamily: "Arial, sans-serif",
    boxSizing: "border-box",
  },
  header: {
    marginBottom: "40px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: "16px",
    flexWrap: "wrap",
  },
  title: {
    fontSize: "42px",
    fontWeight: 600,
    margin: 0,
  },
  buttonGroup: {
    display: "flex",
    gap: "16px",
    flexWrap: "wrap",
  },
  actionButton: {
    border: "3px solid black",
    background: "white",
    padding: "12px 20px",
    fontSize: "18px",
    fontWeight: 600,
    cursor: "pointer",
  },
  mainGrid: {
    display: "grid",
    gridTemplateColumns: "1.6fr 1fr",
    gap: "40px",
  },
  sectionBox: {
    border: "3px solid black",
    background: "#efefef",
    padding: "32px",
    boxSizing: "border-box",
  },
  logoBox: {
    height: "160px",
    border: "3px dashed black",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#f8f8f8",
  },
  logoText: {
    fontSize: "24px",
    fontWeight: 600,
  },
  logsSectionSpacing: {
    marginTop: "32px",
  },
  sectionTitle: {
    margin: 0,
    fontSize: "26px",
    fontWeight: 500,
  },
  logsList: {
    marginTop: "32px",
  },
  logCard: {
    display: "grid",
    gridTemplateColumns: "1fr 140px",
    minHeight: "140px",
    border: "3px solid black",
    background: "#f5f5f5",
    boxSizing: "border-box",
  },
  logTextArea: {
    padding: "24px",
  },
  logMessage: {
    margin: 0,
    fontSize: "22px",
    lineHeight: 1.2,
  },
  logTimestamp: {
    marginTop: "16px",
    marginBottom: 0,
    fontSize: "18px",
  },
  logButtonArea: {
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
  },
  viewButton: {
    border: "3px solid black",
    background: "white",
    padding: "12px 24px",
    fontSize: "20px",
    fontWeight: 600,
    cursor: "pointer",
  },
  paginationWrap: {
    marginTop: "40px",
    display: "flex",
    justifyContent: "center",
  },
  pagination: {
    display: "flex",
    alignItems: "center",
    borderRadius: "12px",
    overflow: "hidden",
    background: "black",
    color: "white",
  },
  paginationButton: {
    background: "black",
    color: "white",
    border: "none",
    padding: "12px 16px",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
  },
  paginationDivider: {
    width: "1px",
    height: "32px",
    background: "#666",
  },
  rightColumn: {
    display: "flex",
    flexDirection: "column",
    gap: "32px",
  },
  atmHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: "16px",
  },
  boxHeadingUpper: {
    margin: 0,
    fontSize: "24px",
    fontWeight: 700,
    textTransform: "uppercase",
  },
  boxHeading: {
    margin: 0,
    fontSize: "24px",
    fontWeight: 700,
  },
  boxText: {
    margin: "16px 0 0 0",
    fontSize: "18px",
  },
  boxParagraph: {
    marginTop: "16px",
    marginBottom: 0,
    fontSize: "18px",
    lineHeight: 1.6,
  },
  infoCircle: {
    width: "40px",
    height: "40px",
    borderRadius: "999px",
    border: "3px solid black",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: "20px",
    flexShrink: 0,
  },
};