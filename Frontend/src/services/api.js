const BASE_URL = "http://localhost:8000";

export const api = {
  // Upload Excel
  uploadCustomers: async (file) => {
    const formData = new FormData();
    formData.append("file", file);

    const res = await fetch(`${BASE_URL}/api/v1/customers/create-bulk`, {
      method: "POST",
      body: formData,
    });

    return res.json();
  },

  // Trigger Call
triggerCall: async (customerId, language, customPrompt) => {
  const res = await fetch(`${BASE_URL}/api/v1/calls/test-livekit-sip`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      customer_id: customerId,
      language,
      custom_prompt: customPrompt,
    }),
  });

  return res.json();
},
  // Get Call History
  getCallHistory: async (customerId) => {
    const res = await fetch(
      `${BASE_URL}/api/v1/customers/${customerId}/call-history`,
    );

    return res.json();
  },
};
