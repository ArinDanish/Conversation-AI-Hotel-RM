import { useState } from "react";
import { api } from "../services/api";

export default function Call() {
  const [customerId, setCustomerId] = useState("");
  const [status, setStatus] = useState("");

  const [loading, setLoading] = useState(false);
  const [language, setLanguage] = useState("en");

  const handleCall = async () => {
    if (loading) return;

    if (!customerId) return alert("Enter Customer ID");

    setLoading(true);
    try {
      const res = await api.triggerCall(customerId, language);
      setStatus(res.message || "Call Triggered ✅");
    } catch (err) {
      setStatus(err.message);
    }
    setLoading(false);
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Trigger Call</h1>

      <div className="bg-white p-6 rounded shadow">
        <input
          type="text"
          placeholder="Enter Customer ID"
          value={customerId}
          onChange={(e) => setCustomerId(e.target.value)}
          className="border p-2 mr-2"
        />
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className="border p-2 mr-2"
        >
          <option value="en">English</option>
          <option value="hi">Hindi</option>
          <option value="ta">Tamil</option>
          <option value="te">Telugu</option>
          <option value="ml">Malayalam</option>
        </select>

        <button
          onClick={handleCall}
          disabled={loading}
          className={`px-4 py-2 rounded text-white transition ${
            loading
              ? "bg-gray-400 cursor-not-allowed"
              : "bg-blue-600 hover:bg-blue-700"
          }`}
        >
          {loading ? "Calling..." : "Call Now"}
        </button>

        {status && <p className="mt-3">{status}</p>}
      </div>
    </div>
  );
}
