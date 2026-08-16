import { useEffect, useState, createContext, useContext } from "react";
import { Navigate, Outlet } from "react-router-dom";
import api from "../api";
import { getToken, clearToken } from "../auth";

const UserContext = createContext(null);
export const useCurrentUser = () => useContext(UserContext);

export default function RequireAuth() {
  const [status, setStatus] = useState("checking"); // checking | ok | fail
  const [user, setUser] = useState(null);

  useEffect(() => {
    if (!getToken()) {
      setStatus("fail");
      return;
    }
    api.get("/auth/me").then(
      (res) => {
        setUser(res.data);
        setStatus("ok");
      },
      () => {
        clearToken();
        setStatus("fail");
      }
    );
  }, []);

  if (status === "checking") return null;
  if (status === "fail") return <Navigate to="/login" replace />;

  return (
    <UserContext.Provider value={user}>
      <Outlet />
    </UserContext.Provider>
  );
}
