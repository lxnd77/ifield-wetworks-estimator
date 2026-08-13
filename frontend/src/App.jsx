import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import ProjectsList from "./pages/ProjectsList";
import ProjectDetail from "./pages/ProjectDetail";
import AdminProducts from "./pages/AdminProducts";
import AdminProductDetail from "./pages/AdminProductDetail";
import AdminCountries from "./pages/AdminCountries";
import AdminCountryDetail from "./pages/AdminCountryDetail";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<ProjectsList />} />
        <Route path="/projects/:id" element={<ProjectDetail />} />
        <Route path="/admin/products" element={<AdminProducts />} />
        <Route path="/admin/products/:id" element={<AdminProductDetail />} />
        <Route path="/admin/countries" element={<AdminCountries />} />
        <Route path="/admin/countries/:id" element={<AdminCountryDetail />} />
      </Route>
    </Routes>
  );
}
