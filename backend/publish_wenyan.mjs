#!/usr/bin/env node
/**
 * publish_wenyan.mjs — 直接调用 @wenyan-md/core 发布文章到微信公众号草稿箱。
 *
 * 用法：
 *   node publish_wenyan.mjs <file_path> [theme_id]
 *
 * 环境变量：
 *   WECHAT_APP_ID      微信公众号 AppID
 *   WECHAT_APP_SECRET  微信公众号 AppSecret
 *
 * 输出（stdout，JSON）：
 *   {"success": true, "media_id": "xxx"}
 *   {"success": false, "error": "..."}
 */

import { createRequire } from "module";
import { readFileSync } from "fs";
import { resolve } from "path";
import { pathToFileURL } from "url";

const require = createRequire(import.meta.url);

// 找 wenyan-md/core 路径（通过 @wenyan-md/mcp 的 node_modules）
const WENYAN_MCP_ROOT = resolve(
  process.env.npm_config_prefix ||
  "C:/Users/anzib/AppData/Roaming/npm",
  "node_modules/@wenyan-md/mcp"
);

async function main() {
  const filePath = process.argv[2];
  const themeId = process.argv[3] || "orangeheart";

  if (!filePath) {
    console.log(JSON.stringify({ success: false, error: "Missing file_path argument" }));
    process.exit(1);
  }

  const absPath = resolve(filePath);
  let content;
  try {
    content = readFileSync(absPath, "utf-8");
  } catch (e) {
    console.log(JSON.stringify({ success: false, error: `Cannot read file: ${e.message}` }));
    process.exit(1);
  }

  // 动态 import renderAndPublish + getInputContent from wenyan-mcp
  let renderAndPublish, getInputContent;
  try {
    const corePath = resolve(WENYAN_MCP_ROOT, "node_modules/@wenyan-md/core/dist/wrapper.js");
    const coreModule = await import(pathToFileURL(corePath).href);
    renderAndPublish = coreModule.renderAndPublish;

    const utilsPath = resolve(WENYAN_MCP_ROOT, "dist/utils.js");
    const utilsModule = await import(pathToFileURL(utilsPath).href);
    getInputContent = utilsModule.getInputContent;
  } catch (e) {
    console.log(JSON.stringify({ success: false, error: `Cannot load wenyan modules: ${e.message}` }));
    process.exit(1);
  }

  const publishOptions = {
    theme: themeId,
    highlight: "solarized-light",
    macStyle: true,
    footnote: true,
    disableStdin: true,
    file: absPath,
  };

  try {
    // Pass empty string as inputContent so getInputContent falls back to reading from file
    const mediaId = await renderAndPublish("", publishOptions, getInputContent);
    console.log(JSON.stringify({ success: true, media_id: mediaId }));
  } catch (e) {
    console.log(JSON.stringify({ success: false, error: e.message || String(e) }));
    process.exit(1);
  }
}

main();
