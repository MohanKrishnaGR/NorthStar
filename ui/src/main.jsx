import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./m3.css";

async function boot() {
  let data = window.__RUN_DATA__;
  if (typeof data === "string") {
    // Dev mode: the placeholder was not replaced — try a sample bundle.
    try {
      const resp = await fetch("./dev_data.json");
      data = resp.ok ? await resp.json() : null;
    } catch {
      data = null; // serve mode (or nothing loaded): App handles both
    }
  }
  createRoot(document.getElementById("root")).render(
    <App initialBundle={data} />
  );
}

boot();
