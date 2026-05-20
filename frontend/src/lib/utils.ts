import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatUKDateTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "N/A";
  try {
    if (dateStr.includes(" - ")) {
      const [start, end] = dateStr.split(" - ");
      const startDate = new Date(start.replace(" ", "T"));
      const endDate = new Date(end.replace(" ", "T"));
      if (isNaN(startDate.getTime())) return dateStr;
      const startFormatted = startDate.toLocaleString("en-GB", {
        day: "2-digit", month: "2-digit", year: "numeric",
        hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
      });
      if (!isNaN(endDate.getTime())) {
        const endFormatted = endDate.toLocaleString("en-GB", {
          day: "2-digit", month: "2-digit", year: "numeric",
          hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
        });
        return `${startFormatted} - ${endFormatted}`;
      }
      return startFormatted;
    }
    const normalized = typeof dateStr === "string" ? dateStr.replace(" ", "T") : dateStr;
    const date = new Date(normalized);
    if (isNaN(date.getTime())) return dateStr;
    return date.toLocaleString("en-GB", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  } catch {
    return dateStr;
  }
}

export function formatUKDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "N/A";
  try {
    const normalized = typeof dateStr === "string" ? dateStr.replace(" ", "T") : dateStr;
    const date = new Date(normalized);
    if (isNaN(date.getTime())) return "N/A";
    return date.toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  } catch {
    return "N/A";
  }
}

export function formatUKTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "N/A";
  try {
    const normalized = typeof dateStr === "string" ? dateStr.replace(" ", "T") : dateStr;
    const date = new Date(normalized);
    if (isNaN(date.getTime())) return "N/A";
    return date.toLocaleTimeString("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  } catch {
    return "N/A";
  }
}
