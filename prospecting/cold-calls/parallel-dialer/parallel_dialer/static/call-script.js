// The call script as the operator reads it during a call. The notepad holds plain text
// with Markdown-style headings, bullets, 👉 replies and *stage directions*; this turns
// it into readable HTML and fills [Name], [My Name] and [Company] for the person on
// the line. Everything is escaped first, so the only markup is what this file adds.
(function () {
  "use strict";

  const escapeHtml = (value) =>
    String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");

  const HONORIFICS = new Set(["dr", "mr", "mrs", "ms", "miss", "mx", "prof"]);

  // "Dr. Jane Roe" -> "Jane". "Close contact" is the dialer's stand-in for a
  // contact without a name, and saying "Hey Close" would be worse than leaving the slot.
  const firstName = (fullName) => {
    const words = String(fullName || "").trim().split(/\s+/).filter(Boolean);
    while (words.length > 1 && HONORIFICS.has(words[0].replace(/\.$/, "").toLowerCase())) {
      words.shift();
    }
    const first = words[0] || "";
    if (!first || (first.toLowerCase() === "close" && words.length === 2 && /^contact$/i.test(words[1]))) {
      return "";
    }
    return first;
  };

  const SLOTS = [
    [/\[my\s*name\]|\{\{\s*my_?name\s*\}\}/gi, "me"],
    [/\[(?:first\s*)?name\]|\{\{\s*(?:first_?name|name)\s*\}\}/gi, "name"],
    [/\[company\]|\{\{\s*company\s*\}\}/gi, "company"],
    [/\[their\s*product\]/gi, "their_product"],
    [/\[product\s*type\]/gi, "product_type"],
    [/\[competitor\s*product\]/gi, "competitor_product"],
    [/\[competitor\s*brand\]/gi, "competitor_brand"],
    [/\[flag\]/gi, "flag"],
    [/\[opener\]/gi, "opener"],
  ];

  // A filled slot is marked so the eye finds it; an empty one stays visible as a slot.
  const fill = (escaped, fills) =>
    SLOTS.reduce(
      (text, [pattern, key]) =>
        text.replace(pattern, (slot) =>
          fills[key]
            ? `<mark class="script-fill">${escapeHtml(fills[key])}</mark>`
            : `<mark class="script-slot">${slot}</mark>`
        ),
      escaped
    );

  const inline = (escaped) =>
    escaped
      .replace(/\*\*([^*]+?)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*\w])\*([^*\s][^*]*?)\*(?![*\w])/g, "$1<em>$2</em>");

  const render = (text, fills = {}) => {
    const out = [];
    let listOpen = false;
    const closeList = () => {
      if (listOpen) out.push("</ul>");
      listOpen = false;
    };
    const format = (raw) => fill(inline(escapeHtml(raw)), fills);

    String(text || "")
      .split(/\r?\n/)
      .forEach((line) => {
        const trimmed = line.trim();
        if (!trimmed) {
          closeList();
          return;
        }
        let match;
        if ((match = trimmed.match(/^###\s+(.*)$/))) {
          closeList();
          out.push(`<h5 class="script-objection">${format(match[1])}</h5>`);
        } else if ((match = trimmed.match(/^##\s+(.*)$/))) {
          closeList();
          out.push(`<h4 class="script-section">${format(match[1])}</h4>`);
        } else if ((match = trimmed.match(/^#\s+(.*)$/))) {
          closeList();
          out.push(`<h3 class="script-title">${format(match[1])}</h3>`);
        } else if ((match = trimmed.match(/^(?:[•\-–]|\*(?=\s))\s*(.*)$/))) {
          if (!listOpen) out.push("<ul>");
          listOpen = true;
          out.push(`<li>${format(match[1])}</li>`);
        } else if (/^\*[^*].*\*$/.test(trimmed)) {
          closeList();
          out.push(`<p class="script-cue">${format(trimmed.slice(1, -1))}</p>`);
        } else if (trimmed.startsWith("👉")) {
          closeList();
          out.push(`<p class="script-reply">${format(trimmed.replace(/^👉\s*/, ""))}</p>`);
        } else {
          closeList();
          out.push(`<p>${format(trimmed)}</p>`);
        }
      });
    closeList();
    return out.join("");
  };

  window.DialerCallScript = { render: render, firstName: firstName };
})();
