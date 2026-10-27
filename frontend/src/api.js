import axios from "axios";
import { getToken, clearToken } from "./auth";
import { requestStarted, requestFinished } from "./loading";

const api = axios.create({ baseURL: "/api" });

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  requestStarted();
  return config;
});

api.interceptors.response.use(
  (res) => {
    requestFinished();
    return res;
  },
  (err) => {
    requestFinished();
    if (err?.response?.status === 401) {
      clearToken();
      if (location.pathname !== "/login") location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export default api;

export const money = (n) =>
  (n ?? 0).toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 2 });

export const num = (n, digits = 2) =>
  (n ?? 0).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
