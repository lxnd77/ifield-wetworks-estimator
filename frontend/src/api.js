import axios from "axios";

const api = axios.create({ baseURL: "/api" });

export default api;

export const money = (n) =>
  (n ?? 0).toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 });

export const num = (n, digits = 2) =>
  (n ?? 0).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
