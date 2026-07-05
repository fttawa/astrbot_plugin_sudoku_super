import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      data += chunk;
    });
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

try {
  const sdkDir = process.argv[2];
  if (!sdkDir) {
    throw new Error("missing sdk dir argument");
  }

  const jsPath = `${sdkDir.replace(/[\\/]$/, "")}/sudoku_wasm.js`;
  const wasmPath = `${sdkDir.replace(/[\\/]$/, "")}/sudoku_wasm_bg.wasm`;
  const wasmModule = await import(pathToFileURL(jsPath).href);
  const wasmBytes = await readFile(wasmPath);
  wasmModule.initSync({ module: wasmBytes });

  const requestText = await readStdin();
  const request = JSON.parse(requestText);
  const responseText = wasmModule.analyze_json(JSON.stringify(request));
  process.stdout.write(responseText);
} catch (error) {
  process.stdout.write(
    JSON.stringify({
      ok: false,
      status: "invalid",
      error: error && error.stack ? error.stack : String(error),
    }),
  );
  process.exitCode = 1;
}
