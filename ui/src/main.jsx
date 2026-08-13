import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./m3.css";

async function boot() {
  let data = window.__RUN_DATA__;
  if (typeof data === "string") {
    // Dev mode: the placeholder was not replaced — load a sample bundle.
    const resp = await fetch("./dev_data.json");
    data = await resp.json();
  }
  createRoot(document.getElementById("root")).render(<App bundle={data} />);
}

boot();
