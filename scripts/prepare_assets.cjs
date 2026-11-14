const fs = require("fs");
for (const weight of [400, 500, 600])
  for (const subset of ["latin", "latin-ext"])
    fs.copyFileSync(
      `node_modules/@fontsource/hanken-grotesk/files/hanken-grotesk-${subset}-${weight}-normal.woff2`,
      `public/fonts/hanken-grotesk-${subset}-${weight}.woff2`,
    );
fs.copyFileSync(
  "node_modules/@fontsource/hanken-grotesk/LICENSE",
  "public/fonts/HANKEN-LICENSE.txt",
);
const names = [
  "layout-dashboard",
  "clipboard-list",
  "search",
  "truck",
  "receipt",
  "settings",
  "mic",
  "bell",
  "menu",
  "x",
  "paperclip",
  "check",
  "repeat-2",
  "package",
  "wallet",
  "plug",
  "chevron-right",
  "chevron-down",
  "log-out",
  "copy",
  "plus",
  "minus",
  "arrow-left",
  "loader-circle",
  "circle-alert",
  "circle-check",
  "calendar",
  "users",
];
fs.writeFileSync(
  "public/icons.svg",
  '<svg xmlns="http://www.w3.org/2000/svg">' +
    names
      .map(
        (n) =>
          `<symbol id="${n}" viewBox="0 0 24 24">` +
          fs
            .readFileSync(`node_modules/lucide-static/icons/${n}.svg`, "utf8")
            .replace(/<svg[^>]*>/, "")
            .replace("</svg>", "") +
          "</symbol>",
      )
      .join("") +
    "</svg>",
);
