import { Link } from "react-router-dom";

export default function Sidebar() {
  return (
    <div className="w-64 h-screen bg-white border-r flex flex-col p-4">
      <h1 className="text-xl font-bold text-blue-600 mb-6">
        Beacon AI
      </h1>

      <nav className="flex flex-col gap-3">
        <Link to="/upload" className="hover:bg-blue-50 p-2 rounded">
          Upload Data
        </Link>
        <Link to="/call" className="hover:bg-blue-50 p-2 rounded">
          Call Trigger
        </Link>
        <Link to="/reports" className="hover:bg-blue-50 p-2 rounded">
          Reports
        </Link>
      </nav>
    </div>
  );
}