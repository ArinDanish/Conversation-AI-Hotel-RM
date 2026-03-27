import { useState } from "react";
import { api } from "../services/api";

export default function Upload() {
  const [file, setFile] = useState(null);
  const [message, setMessage] = useState("");

  const handleUpload = async () => {
    if (!file) return alert("Select a file");

    const res = await api.uploadCustomers(file);
    setMessage("Upload Successful ✅");
    console.log(res);
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-4">Upload Excel</h1>

      <div className="bg-white p-6 rounded shadow">
        <input
          type="file"
          onChange={(e) => setFile(e.target.files[0])}
          className="mb-4"
        />

        <button
          onClick={handleUpload}
          className="bg-blue-600 text-white px-4 py-2 rounded"
        >
          Upload
        </button>

        {message && <p className="mt-3 text-green-600">{message}</p>}
      </div>
    </div>
  );
}