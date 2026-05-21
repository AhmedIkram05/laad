import { useContext } from "react";
import { RAGContext } from "./RAGProvider";

export function useRAG() {
  const ctx = useContext(RAGContext);
  if (!ctx) {
    throw new Error("useRAG must be used within a RAGProvider");
  }
  return ctx;
}
