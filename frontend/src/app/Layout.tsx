import { Outlet, Link } from "react-router-dom";

export default function Layout() {
  return (
    <div className="min-h-screen bg-midnightCharcoal text-warmWhite flex flex-col">
      <header className="bg-foxAmber px-6 py-3 flex items-center gap-3 shadow-lg">
        <Link to="/" className="flex items-center gap-2 text-midnightCharcoal font-bold text-xl tracking-tight hover:opacity-90 transition-opacity">
          <span className="text-2xl">🦊</span>
          <span>FoxSay</span>
        </Link>
      </header>
      <main className="flex-1 bg-warmWhite text-midnightCharcoal overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
