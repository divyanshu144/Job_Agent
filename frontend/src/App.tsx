import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { ProfileSetup } from "./pages/ProfileSetup";
import { AnalyseJob } from "./pages/AnalyseJob";
import { Results } from "./pages/Results";
import { History } from "./pages/History";

const link = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-2 text-sm font-medium rounded-md ${isActive ? "bg-blue-100 text-blue-700" : "text-slate-600 hover:text-slate-900"}`;

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-50">
        <nav className="border-b bg-white px-6 py-3 flex items-center gap-4">
          <span className="font-bold text-slate-900 mr-4">JobFit</span>
          <NavLink to="/" end className={link}>Profile</NavLink>
          <NavLink to="/analyse" className={link}>Analyse</NavLink>
          <NavLink to="/history" className={link}>History</NavLink>
        </nav>
        <main className="py-8">
          <Routes>
            <Route path="/" element={<ProfileSetup />} />
            <Route path="/analyse" element={<AnalyseJob />} />
            <Route path="/results/:id" element={<Results />} />
            <Route path="/history" element={<History />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
