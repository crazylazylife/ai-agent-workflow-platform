import "./globals.css";

export const metadata = { title: "AWP Dashboard" };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <header className="topbar">
          <strong>AI Agent Workflow Platform</strong>
          <nav>
            <a href="/">Runs</a>
            <a href="/approvals">Approvals</a>
            <a href="/metrics">Metrics</a>
            <a href="/evals">Evals</a>
          </nav>
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
