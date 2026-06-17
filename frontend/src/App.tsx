import { BrowserRouter, Routes, Route, NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  BarChart3,
  BriefcaseBusiness,
  Compass,
  FileClock,
  FileSearch,
  Files,
  FolderCheck,
  LogOut,
  MailPlus,
  Menu,
  Sparkles,
  UserRound,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { Dashboard } from "./pages/Dashboard";
import { MyResults } from "./pages/MyResults";
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

const navLink = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
    isActive
      ? "bg-blue-50 text-blue-700 ring-1 ring-blue-100"
      : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-950"
  }`;

const pageTitles: Record<string, string> = {
  "/": "Workspace",
  "/profile": "Profile",
  "/analyse": "Submit Role",
  "/results": "Application Packages",
  "/campaign": "Campaigns",
  "/discover": "Role Discovery",
  "/saved": "Saved Roles",
  "/costs": "Operations",
  "/admin/invites": "Invites",
};

function Shell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  if (!user) {
    return (
      <main className="min-h-screen bg-[#f6f5f2] text-zinc-950">
        {children}
      </main>
    );
  }

  const title =
    pageTitles[location.pathname] ??
    (location.pathname.startsWith("/results") ? "Application Package" : "JobFit");
  const linkClass = navLink;

  const nav = (
    <nav className="space-y-1">
      <NavLink to="/" end className={linkClass} onClick={() => setMobileOpen(false)}>
        <FileClock className="size-4" />
        <span>Workspace</span>
      </NavLink>
      <NavLink to="/analyse" className={linkClass} onClick={() => setMobileOpen(false)}>
        <FileSearch className="size-4" />
        <span>Submit Role</span>
      </NavLink>
      <NavLink to="/results" end className={linkClass} onClick={() => setMobileOpen(false)}>
        <Files className="size-4" />
        <span>Application Packages</span>
      </NavLink>
      <NavLink to="/profile" className={linkClass} onClick={() => setMobileOpen(false)}>
        <UserRound className="size-4" />
        <span>Profile</span>
      </NavLink>
      {user.is_admin && (
        <>
          <div className="px-3 pb-1 pt-5 text-[11px] font-semibold uppercase tracking-[0.18em] text-zinc-400">
            Operations
          </div>
          <NavLink to="/discover" className={linkClass} onClick={() => setMobileOpen(false)}>
            <Compass className="size-4" />
            <span>Role Discovery</span>
          </NavLink>
          <NavLink to="/campaign" className={linkClass} onClick={() => setMobileOpen(false)}>
            <BriefcaseBusiness className="size-4" />
            <span>Campaigns</span>
          </NavLink>
          <NavLink to="/saved" className={linkClass} onClick={() => setMobileOpen(false)}>
            <FolderCheck className="size-4" />
            <span>Saved Roles</span>
          </NavLink>
          <NavLink to="/costs" className={linkClass} onClick={() => setMobileOpen(false)}>
            <BarChart3 className="size-4" />
            <span>Operations</span>
          </NavLink>
          <NavLink to="/admin/invites" className={linkClass} onClick={() => setMobileOpen(false)}>
            <MailPlus className="size-4" />
            <span>Invites</span>
          </NavLink>
        </>
      )}
    </nav>
  );

  return (
    <div className="min-h-screen bg-[#f6f5f2] text-zinc-950">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-72 border-r border-zinc-200 bg-white px-4 py-5 lg:block">
        <div className="flex items-center gap-3 px-2">
          <div className="flex size-10 items-center justify-center rounded-xl bg-zinc-950 text-white">
            <Sparkles className="size-5" />
          </div>
          <div>
            <p className="text-sm font-bold leading-tight text-zinc-950">JobFit</p>
            <p className="text-xs leading-tight text-zinc-500">Application support service</p>
          </div>
        </div>
        <div className="mt-8">{nav}</div>
        <div className="absolute bottom-5 left-4 right-4 rounded-2xl border border-zinc-200 bg-[#fafafa] p-3 shadow-[0_18px_60px_rgba(24,24,27,0.08)]">
          <p className="truncate text-sm font-medium text-zinc-900">{user.email}</p>
          <div className="mt-3 flex items-center justify-between gap-2">
            {user.is_admin ? (
              <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                admin
              </span>
            ) : (
              <span className="rounded-full border border-zinc-200 px-2 py-0.5 text-xs font-medium text-zinc-500">
                client
              </span>
            )}
            <button
              onClick={handleLogout}
              className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 px-2.5 py-1.5 text-xs font-medium text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-950"
            >
              <LogOut className="size-3.5" />
              Sign out
            </button>
          </div>
        </div>
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 bg-white lg:hidden">
          <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-4">
            <div className="flex items-center gap-3">
              <div className="flex size-9 items-center justify-center rounded-lg bg-zinc-950 text-white">
                <Sparkles className="size-4" />
              </div>
              <span className="text-sm font-bold">JobFit</span>
            </div>
            <button onClick={() => setMobileOpen(false)} className="rounded-lg border border-zinc-200 p-2">
              <X className="size-4" />
            </button>
          </div>
          <div className="p-4">{nav}</div>
        </div>
      )}

      <div className="lg:pl-72">
        <header className="sticky top-0 z-20 border-b border-zinc-200 bg-[#f6f5f2]/90 backdrop-blur-xl">
          <div className="flex min-h-16 items-center justify-between gap-3 px-4 sm:px-6 lg:px-8">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setMobileOpen(true)}
                className="rounded-lg border border-zinc-200 p-2 text-zinc-700 lg:hidden"
              >
                <Menu className="size-4" />
              </button>
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.22em] text-zinc-500">
                  {location.pathname.startsWith("/costs") || location.pathname.startsWith("/discover") || location.pathname.startsWith("/saved") || location.pathname.startsWith("/admin")
                    ? "Operations"
                    : "Client portal"}
                </p>
                <h1 className="text-base font-semibold text-zinc-950 sm:text-lg">{title}</h1>
              </div>
            </div>
            {user.is_admin && (
              <div className="hidden items-center gap-2 rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-xs font-medium text-zinc-500 shadow-sm sm:flex">
                <span className="size-2 rounded-full bg-zinc-400" />
                Operations available
              </div>
            )}
          </div>
        </header>
        <main className="client-main relative min-h-[calc(100vh-4rem)] px-4 py-8 sm:px-6 lg:px-8">
          <div className="relative z-10">{children}</div>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Shell>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
            <Route path="/profile" element={<ProtectedRoute><ProfileSetup /></ProtectedRoute>} />
            <Route path="/analyse" element={<ProtectedRoute><AnalyseJob /></ProtectedRoute>} />
            <Route path="/results" element={<ProtectedRoute><MyResults /></ProtectedRoute>} />
            <Route path="/results/:id" element={<ProtectedRoute><Results /></ProtectedRoute>} />
            <Route path="/campaign" element={<ProtectedRoute requireAdmin><Campaign /></ProtectedRoute>} />
            <Route path="/discover" element={<ProtectedRoute requireAdmin><Discover /></ProtectedRoute>} />
            <Route path="/saved" element={<ProtectedRoute requireAdmin><Saved /></ProtectedRoute>} />
            <Route path="/costs" element={<ProtectedRoute requireAdmin><Costs /></ProtectedRoute>} />
            <Route path="/admin/invites" element={<ProtectedRoute requireAdmin><AdminInvites /></ProtectedRoute>} />
          </Routes>
        </Shell>
      </AuthProvider>
    </BrowserRouter>
  );
}
