import {
  BrowserRouter,
  Routes,
  Route,
  NavLink,
  Navigate,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import {
  BarChart3,
  Bell,
  BriefcaseBusiness,
  ChevronRight,
  Compass,
  FileClock,
  FileSearch,
  FileText,
  Files,
  FolderCheck,
  LogOut,
  MailPlus,
  Menu,
  Search,
  Settings,
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
import { ResumeEditor } from "./pages/ResumeEditor";
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
  `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150 ${
    isActive
      ? "bg-[rgba(91,91,214,0.18)] text-white"
      : "text-[#9898a8] hover:bg-[rgba(255,255,255,0.07)] hover:text-[#e8e8ef]"
  }`;

const pageTitles: Record<string, string> = {
  "/": "Workspace",
  "/profile": "Profile",
  "/analyse": "Submit Role",
  "/results": "Application Packages",
  "/resume": "Resume Editor",
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
    (location.pathname.startsWith("/results")
      ? "Application Package"
      : location.pathname.startsWith("/resume")
        ? "Resume Editor"
        : "JobFit");
  const linkClass = navLink;
  const initials = user.email.slice(0, 2).toUpperCase();
  const isOperations =
    location.pathname.startsWith("/costs") ||
    location.pathname.startsWith("/discover") ||
    location.pathname.startsWith("/campaign") ||
    location.pathname.startsWith("/saved") ||
    location.pathname.startsWith("/admin");

  const nav = (
    <nav className="space-y-1">
      <NavLink to="/" end className={linkClass} onClick={() => setMobileOpen(false)}>
        <FileClock className="size-4" />
        <span>Workspace</span>
        {location.pathname === "/" && <ChevronRight className="ml-auto size-3.5 text-[#6060d0]" />}
      </NavLink>
      <NavLink to="/analyse" className={linkClass} onClick={() => setMobileOpen(false)}>
        <FileSearch className="size-4" />
        <span>Submit Role</span>
      </NavLink>
      <NavLink to="/results" end className={linkClass} onClick={() => setMobileOpen(false)}>
        <Files className="size-4" />
        <span>Application Packages</span>
      </NavLink>
      <NavLink to="/resume" className={linkClass} onClick={() => setMobileOpen(false)}>
        <FileText className="size-4" />
        <span>Resume Editor</span>
      </NavLink>
      <NavLink to="/profile" className={linkClass} onClick={() => setMobileOpen(false)}>
        <UserRound className="size-4" />
        <span>Profile</span>
      </NavLink>
      {user.is_admin && (
        <>
          <div className="px-3 pb-1 pt-5 text-[10px] font-mono uppercase tracking-[0.15em] text-[#3a3a4a]">
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
    <div className="min-h-screen bg-[#f7f7f5] text-[#0f0f17]">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col bg-[#0f0f17] lg:flex">
        <div className="border-b border-[rgba(255,255,255,0.07)] px-5 py-5">
          <div className="flex items-center gap-2.5">
            <div className="flex size-7 items-center justify-center rounded-lg bg-[#5b5bd6] text-white">
              <Sparkles className="size-3.5" />
            </div>
            <div>
              <p className="font-semibold leading-none tracking-[-0.03em] text-white">JobFit</p>
              <p className="mt-0.5 font-mono text-xs tracking-wide text-[#4a4a5a]">Your Hunting Partner</p>
            </div>
          </div>
        </div>

        <div className="border-b border-[rgba(255,255,255,0.07)] px-4 py-4">
          <div className="flex items-center gap-3">
            <div className="flex size-8 items-center justify-center rounded-full bg-gradient-to-br from-[#5b5bd6] to-[#9333ea] text-xs font-semibold text-white">
              {initials}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm leading-tight text-[#e8e8ef]">{user.email}</p>
              <p className="truncate text-xs text-[#4a4a5a]">{user.is_admin ? "admin" : "client"}</p>
            </div>
            <Settings className="size-3.5 text-[#3a3a4a]" />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-4">{nav}</div>

        <div className="px-4 pb-5">
          <div className="rounded-xl border border-[rgba(255,255,255,0.07)] bg-[rgba(255,255,255,0.04)] p-3.5">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs text-[#9898a8]">Profile Readiness</span>
              <span className="font-mono text-xs text-[#8888f0]">Live</span>
            </div>
            <div className="h-1 rounded-full bg-[rgba(255,255,255,0.07)]">
              <div className="h-full w-3/4 rounded-full bg-gradient-to-r from-[#5b5bd6] to-[#9333ea]" />
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-[#4a4a5a]">
              Keep your profile updated before submitting roles.
            </p>
          </div>
          <button
            onClick={handleLogout}
            className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg border border-[rgba(255,255,255,0.08)] px-3 py-2 text-xs font-medium text-[#9898a8] transition-colors hover:bg-[rgba(255,255,255,0.06)] hover:text-white"
          >
            <LogOut className="size-3.5" />
            Sign out
          </button>
        </div>
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 bg-[#0f0f17] lg:hidden">
          <div className="flex items-center justify-between border-b border-[rgba(255,255,255,0.07)] px-4 py-4">
            <div className="flex items-center gap-3">
              <div className="flex size-9 items-center justify-center rounded-lg bg-[#5b5bd6] text-white">
                <Sparkles className="size-4" />
              </div>
              <span className="text-sm font-bold text-white">JobFit</span>
            </div>
            <button onClick={() => setMobileOpen(false)} className="rounded-lg border border-[rgba(255,255,255,0.1)] p-2 text-white">
              <X className="size-4" />
            </button>
          </div>
          <div className="flex h-[calc(100%-4.5rem)] flex-col">
            <div className="flex-1 overflow-y-auto p-4">{nav}</div>
            <div className="border-t border-[rgba(255,255,255,0.07)] p-4">
              <div className="mb-3 flex items-center gap-3">
                <div className="flex size-8 items-center justify-center rounded-full bg-gradient-to-br from-[#5b5bd6] to-[#9333ea] text-xs font-semibold text-white">
                  {initials}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm leading-tight text-[#e8e8ef]">{user.email}</p>
                  <p className="truncate text-xs text-[#4a4a5a]">{user.is_admin ? "admin" : "client"}</p>
                </div>
              </div>
              <button
                onClick={() => {
                  setMobileOpen(false);
                  handleLogout();
                }}
                className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-[rgba(255,255,255,0.08)] px-3 py-2.5 text-sm font-medium text-[#9898a8] transition-colors hover:bg-[rgba(255,255,255,0.06)] hover:text-white"
              >
                <LogOut className="size-4" />
                Sign out
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 h-14 border-b border-[rgba(0,0,0,0.06)] bg-[#f7f7f5]/90 backdrop-blur-sm">
          <div className="flex h-full items-center justify-between gap-3 px-4 sm:px-6">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setMobileOpen(true)}
                className="rounded-lg border border-[rgba(0,0,0,0.08)] p-2 text-[#71717a] lg:hidden"
              >
                <Menu className="size-4" />
              </button>
              <div className="flex items-center gap-2 text-sm">
                <span className="hidden font-mono text-xs uppercase tracking-[0.1em] text-[#9898a8] sm:block">
                  JobFit
                </span>
                <span className="hidden text-[#d4d4d8] sm:block">/</span>
                <span className="text-sm text-[#0f0f17]">{title}</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button className="hidden size-8 items-center justify-center rounded-lg text-[#71717a] transition-colors hover:bg-[rgba(0,0,0,0.04)] sm:flex">
                <Search className="size-4" />
              </button>
              {user.is_admin && (
                <div className="hidden items-center gap-2 rounded-lg border border-[rgba(0,0,0,0.06)] bg-white px-3 py-1.5 text-xs font-medium text-[#71717a] shadow-sm sm:flex">
                  <span className="size-1.5 rounded-full bg-[#9898a8]" />
                  {isOperations ? "Operations" : "Operations available"}
                </div>
              )}
              <button className="relative hidden size-8 items-center justify-center rounded-lg text-[#71717a] transition-colors hover:bg-[rgba(0,0,0,0.04)] sm:flex">
                <Bell className="size-4" />
                <span className="absolute right-1.5 top-1.5 size-1.5 rounded-full bg-[#5b5bd6]" />
              </button>
              <div className="flex size-7 items-center justify-center rounded-full bg-gradient-to-br from-[#5b5bd6] to-[#9333ea] text-xs font-semibold text-white">
                {initials}
              </div>
            </div>
          </div>
        </header>
        <main className="client-main relative min-h-[calc(100vh-3.5rem)] px-4 py-8 sm:px-6">
          <div className="relative z-10">{children}</div>
        </main>
      </div>
    </div>
  );
}

// The standalone per-analysis resume editor page was retired; its editor now
// lives in the Results page's Resume tab. Send any bookmarked fork-editor URL
// to that analysis's Results page (the `:id` the Results route expects).
function ResumeAnalysisRedirect() {
  const { analysisId } = useParams<{ analysisId: string }>();
  return <Navigate to={`/results/${analysisId}`} replace />;
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
            <Route path="/resume" element={<ProtectedRoute><ResumeEditor /></ProtectedRoute>} />
            {/* The per-analysis resume editor now lives inside the Results page's
                Resume tab. Redirect any bookmarked fork-editor URL there. */}
            <Route path="/resume/analysis/:analysisId" element={<ResumeAnalysisRedirect />} />
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
