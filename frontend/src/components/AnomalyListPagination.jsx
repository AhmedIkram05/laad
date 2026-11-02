/** First/Prev/Next/Last pagination for the anomaly list. */
function AnomalyListPagination({ safePage, totalPages, setCurrentPage }) {
  if (totalPages <= 1) return null;
  return (
    <div className="flex justify-center gap-2">
      <button onClick={() => setCurrentPage(1)} disabled={safePage === 1} className="px-3 py-1.5 border rounded disabled:opacity-50">First</button>
      <button onClick={() => setCurrentPage((p) => Math.max(1, p - 1))} disabled={safePage === 1} className="px-3 py-1.5 border rounded disabled:opacity-50">Prev</button>
      <span className="px-3 py-1.5">Page {safePage} of {totalPages}</span>
      <button onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))} disabled={safePage === totalPages} className="px-3 py-1.5 border rounded disabled:opacity-50">Next</button>
      <button onClick={() => setCurrentPage(totalPages)} disabled={safePage === totalPages} className="px-3 py-1.5 border rounded disabled:opacity-50">Last</button>
    </div>
  );
}

export default AnomalyListPagination;
