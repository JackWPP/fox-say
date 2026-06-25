import { Outlet, Link } from "react-router-dom";

export default function Layout() {
  return (
    <div className="min-h-screen bg-slate-50 text-midnightCharcoal flex flex-col">
      <header className="bg-white h-14 px-6 flex items-center gap-3 shadow-subtle border-b border-slate-200">
        <Link to="/" className="flex items-center gap-2 text-midnightCharcoal font-bold text-xl tracking-tight hover:opacity-80 transition-opacity">
          <span className="text-2xl">🦊</span>
          <span>FoxSay</span>
        </Link>
      </header>
      <main className="flex-1 bg-slate-50 text-midnightCharcoal overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
