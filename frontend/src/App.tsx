import { BrowserRouter, Routes, Route, NavLink, useNavigate } from "react-router-dom";
import {
  BarChart3,
  BriefcaseBusiness,
  Compass,
  FileSearch,
  FolderCheck,
  LogOut,
  MailPlus,
  Sparkles,
  UserRound,
} from "lucide-react";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { ProfileSetup } from "./pages/ProfileSetup";
import { AnalyseJob } from "./pages/AnalyseJob";
import { Results } from "./pages/Results";
import { Saved } from "./pages/Saved";
import { Discover } from "./pages/Discover";
import { Costs } from "./pages/Costs";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";
import { ForgotPassword } from "./pages/ForgotPassword";
import { ResetPassword } from "./pages/ResetPassword";
import { AdminInvites } from "./pages/AdminInvites";
import { Campaign } from "./pages/Campaign";

const link = ({ isActive }: { isActive: boolean }) =>
  `inline-flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
    isActive
      ? "bg-indigo-950 text-white shadow-sm"
      : "text-slate-600 hover:bg-white hover:text-slate-950"
  }`;

function Nav() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  if (!user) return null;

  return (
    <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-[#f7f9fc]/90 backdrop-blur">
      <nav className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-4 py-3 sm:flex-nowrap sm:px-5">
        <div className="order-1 flex shrink-0 items-center gap-3">
          <div className="flex size-9 items-center justify-center rounded-lg bg-indigo-950 text-white shadow-sm shadow-indigo-950/10">
            <Sparkles className="size-4" />
          </div>
          <div className="hidden sm:block">
            <p className="text-sm font-bold leading-tight text-slate-950">JobFit</p>
            <p className="text-xs leading-tight text-slate-500">AI application desk</p>
          </div>
        </div>
        <div className="order-3 flex w-full min-w-0 items-center gap-1 overflow-x-auto py-1 sm:order-2 sm:w-auto sm:flex-1">
          <NavLink to="/" end className={link}><UserRound className="size-4" /><span>Profile</span></NavLink>
          <NavLink to="/analyse" className={link}><FileSearch className="size-4" /><span>Analyse</span></NavLink>
          <NavLink to="/campaign" className={link}><BriefcaseBusiness className="size-4" /><span>Campaign</span></NavLink>
          {user.is_admin && <NavLink to="/discover" className={link}><Compass className="size-4" /><span>Discover</span></NavLink>}
          {user.is_admin && <NavLink to="/saved" className={link}><FolderCheck className="size-4" /><span>Saved</span></NavLink>}
          {user.is_admin && <NavLink to="/costs" className={link}><BarChart3 className="size-4" /><span>Costs</span></NavLink>}
          {user.is_admin && <NavLink to="/admin/invites" className={link}><MailPlus className="size-4" /><span>Invites</span></NavLink>}
        </div>
        <div className="order-2 ml-auto flex shrink-0 items-center gap-2 rounded-xl border border-slate-200 bg-white/90 px-2.5 py-2 shadow-sm shadow-slate-200/60 sm:order-3">
          <span className="hidden max-w-[170px] truncate text-xs font-medium text-slate-600 lg:inline">{user.email}</span>
        {user.is_admin && (
          <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700">admin</span>
        )}
        <button
          onClick={handleLogout}
          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2 py-1 text-xs font-medium text-slate-500 transition-colors hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900"
        >
          <LogOut className="size-3.5" />
          <span className="hidden sm:inline">Sign out</span>
        </button>
      </div>
      </nav>
    </header>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,#eef2ff_0,#f7f9fc_28%,#eef3f8_100%)] text-slate-950">
          <Nav />
          <main className="mx-auto max-w-7xl px-4 py-6 sm:px-5 sm:py-8">
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/forgot-password" element={<ForgotPassword />} />
              <Route path="/reset-password" element={<ResetPassword />} />
              <Route path="/" element={<ProtectedRoute><ProfileSetup /></ProtectedRoute>} />
              <Route path="/analyse" element={<ProtectedRoute><AnalyseJob /></ProtectedRoute>} />
              <Route path="/results/:id" element={<ProtectedRoute><Results /></ProtectedRoute>} />
              <Route path="/campaign" element={<ProtectedRoute><Campaign /></ProtectedRoute>} />
              <Route path="/discover" element={<ProtectedRoute><Discover /></ProtectedRoute>} />
              <Route path="/saved" element={<ProtectedRoute><Saved /></ProtectedRoute>} />
              <Route path="/costs" element={<ProtectedRoute><Costs /></ProtectedRoute>} />
              <Route path="/admin/invites" element={<ProtectedRoute><AdminInvites /></ProtectedRoute>} />
            </Routes>
          </main>
        </div>
      </AuthProvider>
    </BrowserRouter>
  );
}
