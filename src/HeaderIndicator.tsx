import { executeInTab, fetchNoCors } from "@decky/api";

import { browsecIconPath } from "./BrowsecIcon";

const fallbackGamepadTabNames = [
  "SP",
  "Steam",
  "SharedJSContext",
  "Steam Shared Context presented by Valve™",
  "Steam Big Picture Mode",
];
const heartbeatMilliseconds = 5_000;
const stateLifetimeMilliseconds = 15_000;
const tabDiscoveryUrl = "http://localhost:8080/json";
const tabOperationTimeoutMilliseconds = 2_000;

let vpnConnected = false;
let indicatorInstalled = false;
let syncChain = Promise.resolve();
let warnedAboutTarget = false;

interface InspectableTab {
  title?: string;
  url?: string;
}

function injectionScript(enabled: boolean) {
  const configuration = JSON.stringify({
    badgeId: "browsec-decky-topbar-badge",
    clockSelectors: [
      "._1HhLUvHH6BZLIOyOE80TVh",
      "#header ._1HhLUvHH6BZLIOyOE80TVh",
    ],
    enabled,
    expiresAt: Date.now() + stateLifetimeMilliseconds,
    iconPath: browsecIconPath,
    styleId: "browsec-decky-topbar-style",
  });

  return `
(function () {
  const config = ${configuration};
  const stateKey = "__browsecDeckyTopbarState";
  const controllerKey = "__browsecDeckyTopbarController";

  function removeIndicator() {
    document
      .querySelectorAll("#" + config.badgeId)
      .forEach((node) => node.remove());
    document.getElementById(config.styleId)?.remove();
  }

  if (!config.enabled) {
    window[stateKey] = { enabled: false, expiresAt: 0 };
    const controller = window[controllerKey];
    if (controller && typeof controller.stop === "function") {
      controller.stop();
    } else {
      removeIndicator();
    }
    return "Browsec top bar indicator removed";
  }

  window[stateKey] = {
    enabled: true,
    expiresAt: config.expiresAt,
  };

  function ownClockText(node) {
    return Array.from(node.childNodes)
      .filter((child) => child.nodeType === Node.TEXT_NODE)
      .map((child) => child.textContent || "")
      .join(" ")
      .trim();
  }

  function findClock() {
    const roots = Array.from(
      document.querySelectorAll(
        "#header,[class*=GamepadHeader],[class*=HeaderStatus],[class*=TopBar]",
      ),
    );
    const isInHeader = (node) =>
      roots.some((root) => root === node || root.contains(node));

    for (const selector of config.clockSelectors) {
      const match = document.querySelector(selector);
      if (match && isInHeader(match)) {
        return match;
      }
    }

    for (const root of roots) {
      const nodes = Array.from(root.querySelectorAll("div,span,button"));
      const match = nodes.find((node) => {
        const text =
          ownClockText(node) || (node.textContent || "").trim();
        return /^\\d{1,2}:\\d{2}(?:\\s|$)/.test(text);
      });
      if (match) {
        return match;
      }
    }

    return null;
  }

  function installStyle() {
    let style = document.getElementById(config.styleId);
    if (!style) {
      style = document.createElement("style");
      style.id = config.styleId;
      document.head.appendChild(style);
    }
    style.textContent = \`
      #\${config.badgeId} {
        align-items: center !important;
        align-self: center !important;
        color: #fff !important;
        display: inline-flex !important;
        flex: 0 0 auto !important;
        height: 1em !important;
        justify-content: center !important;
        line-height: 1 !important;
        margin-left: 0.45em !important;
        opacity: 0.95 !important;
        pointer-events: none !important;
        position: relative !important;
        transform: translateY(-1px) !important;
        vertical-align: middle !important;
        width: 1em !important;
      }
      #\${config.badgeId} svg {
        display: block !important;
        fill: none !important;
        height: 1em !important;
        overflow: visible !important;
        stroke: currentColor !important;
        width: 1em !important;
      }
    \`;
  }

  function ensureIndicator() {
    const state = window[stateKey];
    if (
      !state ||
      !state.enabled ||
      Date.now() > Number(state.expiresAt || 0)
    ) {
      const controller = window[controllerKey];
      if (controller && typeof controller.stop === "function") {
        controller.stop();
      } else {
        removeIndicator();
      }
      return false;
    }

    const clock = findClock();
    if (!clock) {
      return false;
    }

    installStyle();
    let badge = document.getElementById(config.badgeId);
    if (!badge) {
      badge = document.createElement("span");
      badge.id = config.badgeId;
      badge.setAttribute("aria-label", "Browsec VPN connected");
      badge.setAttribute("role", "status");
      badge.setAttribute("title", "Browsec VPN connected");
      badge.innerHTML =
        '<svg aria-hidden="true" viewBox="0 0 50.8 50.8">' +
        '<path d="' +
        config.iconPath +
        '" stroke-linecap="round" stroke-linejoin="round" ' +
        'stroke-width="3.175"></path></svg>';
    }

    if (badge.parentNode !== clock) {
      clock.appendChild(badge);
    }
    return true;
  }

  ensureIndicator();

  if (!window[controllerKey]) {
    let queued = false;
    const queueEnsure = () => {
      if (queued) {
        return;
      }
      queued = true;
      window.setTimeout(() => {
        queued = false;
        try {
          ensureIndicator();
        } catch (_) {}
      }, 60);
    };
    const observer = new MutationObserver(queueEnsure);
    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
    });
    const interval = window.setInterval(ensureIndicator, 1_000);

    window[controllerKey] = {
      stop() {
        observer.disconnect();
        window.clearInterval(interval);
        removeIndicator();
        delete window[controllerKey];
      },
    };
  }

  return "Browsec top bar indicator active";
})();
`;
}

function withTimeout<T>(operation: Promise<T>) {
  return new Promise<T>((resolve, reject) => {
    const timeout = window.setTimeout(
      () => reject(new Error("Steam tab operation timed out")),
      tabOperationTimeoutMilliseconds,
    );
    operation.then(
      (value) => {
        window.clearTimeout(timeout);
        resolve(value);
      },
      (error: unknown) => {
        window.clearTimeout(timeout);
        reject(error);
      },
    );
  });
}

function isGamepadTab(tab: InspectableTab) {
  const title = tab.title?.trim() ?? "";
  const url = tab.url ?? "";
  const isSharedContext =
    fallbackGamepadTabNames.includes(title) &&
    (url.includes("https://steamloopback.host/routes/") ||
      url.includes("https://steamloopback.host/index.html"));

  return (
    isSharedContext ||
    title === "Steam Big Picture Mode" ||
    title.startsWith("QuickAccess") ||
    title.startsWith("MainMenu") ||
    url.includes("Valve%20Steam%20Gamepad") ||
    url.includes("Valve Steam Gamepad/default")
  );
}

async function resolveGamepadTabs() {
  try {
    const response = await withTimeout(fetchNoCors(tabDiscoveryUrl));
    if (!response.ok) {
      return fallbackGamepadTabNames;
    }
    const tabs = (await response.json()) as InspectableTab[];
    const titles = new Set<string>();
    for (const tab of Array.isArray(tabs) ? tabs : []) {
      const title = tab.title?.trim();
      if (title && isGamepadTab(tab)) {
        titles.add(title);
      }
    }
    if (titles.size > 0) {
      return Array.from(titles);
    }
  } catch {
    // Fall back to the shared-context names used by older Steam clients.
  }

  return fallbackGamepadTabNames;
}

async function executeInGamepadTabs(script: string) {
  const tabs = await resolveGamepadTabs();
  const results = await Promise.all(
    tabs.map(async (tab) => {
      try {
        const result = await withTimeout(
          executeInTab(tab, false, script),
        );
        return result.success;
      } catch {
        return false;
      }
    }),
  );

  for (const success of results) {
    if (success) {
      warnedAboutTarget = false;
      return true;
    }
  }

  return false;
}

async function removeFromFallbackTabs(script: string) {
  for (const tab of fallbackGamepadTabNames) {
    try {
      await withTimeout(executeInTab(tab, false, script));
    } catch {
      // Ignore tabs that do not exist during plugin cleanup.
    }
  }
}

function queueSync() {
  syncChain = syncChain
    .catch(() => undefined)
    .then(async () => {
      const enabled = indicatorInstalled && vpnConnected;
      const script = injectionScript(enabled);
      const success = await executeInGamepadTabs(script);
      if (!enabled && !success) {
        await removeFromFallbackTabs(script);
      }
      if (enabled && !success && !warnedAboutTarget) {
        warnedAboutTarget = true;
        console.warn(
          "[Browsec Decky] Could not reach the Steam Gamepad UI tab",
        );
      }
    });
}

export function setHeaderVpnConnected(connected: boolean) {
  vpnConnected = connected;
  if (indicatorInstalled) {
    queueSync();
  }
}

export function installHeaderIndicator() {
  indicatorInstalled = true;
  queueSync();
  const heartbeat = window.setInterval(
    queueSync,
    heartbeatMilliseconds,
  );

  return () => {
    indicatorInstalled = false;
    vpnConnected = false;
    window.clearInterval(heartbeat);
    queueSync();
  };
}
