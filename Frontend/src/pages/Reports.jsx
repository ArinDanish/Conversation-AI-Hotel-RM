import { useState } from "react";
import { api } from "../services/api";

export default function Reports() {
  const [customerId, setCustomerId] = useState("");
  const [calls, setCalls] = useState([]);

  const fetchReports = async () => {
    try {
      const res = await api.getCallHistory(customerId);

      if (res.calls && Array.isArray(res.calls)) {
        setCalls(res.calls);
      } else {
        console.error("Invalid response:", res);
        setCalls([]);
      }
    } catch (err) {
      console.error(err);
      setCalls([]);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Reports</h1>

      <div className="bg-white p-4 rounded shadow mb-4">
        <input
          type="text"
          placeholder="Customer ID"
          value={customerId}
          onChange={(e) => setCustomerId(e.target.value)}
          className="border p-2 mr-2"
        />
        <button
          onClick={fetchReports}
          className="bg-blue-600 text-white px-4 py-2 rounded"
        >
          Fetch
        </button>
      </div>

      <div className="grid gap-4">
        {calls.recording_url && (
          <div className="mt-3">
            <audio controls className="w-full">
              <source src={calls.recording_url} type="audio/wav" />
            </audio>
          </div>
        )}
        {calls.map((call, i) => (
          <div
            key={i}
            className="bg-white p-4 rounded-xl shadow hover:shadow-md transition"
          >
            <p className="text-sm text-gray-500">{call.call_date}</p>

            <p className="mt-1">
              <b>Status:</b> {call.status}
            </p>

            <p>
              <b>Sentiment:</b>
              <span
                className={`ml-2 px-2 py-1 rounded text-white text-xs ${
                  call.sentiment === "positive"
                    ? "bg-green-500"
                    : call.sentiment === "negative"
                      ? "bg-red-500"
                      : "bg-gray-500"
                }`}
              >
                {call.sentiment}
              </span>
            </p>

            <p>
              <b>Duration:</b> {call.duration} sec
            </p>

            {call.recording_url && (
              <audio
                controls
                className="w-full mt-3"
                src={call.recording_url}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
