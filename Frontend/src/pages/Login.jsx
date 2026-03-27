export default function Login() {
  return (
    <div className="h-screen flex items-center justify-center bg-blue-50">
      <div className="bg-white p-8 rounded shadow w-80">
        <h1 className="text-xl font-bold mb-4 text-blue-600">
          Login
        </h1>

        <input
          type="text"
          placeholder="Email"
          className="border p-2 w-full mb-3"
        />
        <input
          type="password"
          placeholder="Password"
          className="border p-2 w-full mb-4"
        />

        <button className="bg-blue-600 text-white w-full py-2 rounded">
          Login
        </button>
      </div>
    </div>
  );
}