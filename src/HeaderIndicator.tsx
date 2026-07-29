import { browsecIconPath } from "./BrowsecIcon";

const indicatorAttribute = "data-browsec-decky-status";
const svgNamespace = "http://www.w3.org/2000/svg";

let vpnConnected = false;
let syncInstalledIndicator: (() => void) | null = null;

export function setHeaderVpnConnected(connected: boolean) {
  vpnConnected = connected;
  syncInstalledIndicator?.();
}

function createIndicator() {
  const indicator = document.createElement("div");
  indicator.setAttribute("aria-label", "Browsec VPN connected");
  indicator.setAttribute(indicatorAttribute, "connected");
  indicator.setAttribute("role", "status");
  indicator.setAttribute("title", "Browsec VPN connected");
  Object.assign(indicator.style, {
    alignItems: "center",
    color: "inherit",
    display: "flex",
    flexShrink: "0",
    height: "32px",
    justifyContent: "center",
    margin: "0 4px",
    pointerEvents: "none",
    width: "28px",
  });

  const svg = document.createElementNS(svgNamespace, "svg");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("fill", "none");
  svg.setAttribute("focusable", "false");
  svg.setAttribute("height", "22");
  svg.setAttribute("viewBox", "0 0 50.8 50.8");
  svg.setAttribute("width", "22");
  Object.assign(svg.style, {
    display: "block",
    flexShrink: "0",
  });

  const path = document.createElementNS(svgNamespace, "path");
  path.setAttribute("d", browsecIconPath);
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");
  path.setAttribute("stroke-width", "3.175");

  svg.append(path);
  indicator.append(svg);
  return indicator;
}

function removeIndicators() {
  document
    .querySelectorAll<HTMLElement>(`[${indicatorAttribute}]`)
    .forEach((indicator) => indicator.remove());
}

export function installHeaderIndicator() {
  let indicator: HTMLElement | null = null;
  let syncing = false;

  const sync = () => {
    if (syncing) {
      return;
    }

    syncing = true;
    try {
      if (!vpnConnected) {
        removeIndicators();
        return;
      }

      const header = document.getElementById("header");
      if (!header) {
        return;
      }

      const existing =
        header.querySelector<HTMLElement>(`[${indicatorAttribute}]`);
      indicator = existing ?? indicator ?? createIndicator();

      const profile = document.getElementById("header_profile");
      let profileAnchor = profile;
      while (
        profileAnchor &&
        profileAnchor.parentElement !== header
      ) {
        profileAnchor = profileAnchor.parentElement;
      }

      if (profileAnchor?.parentElement === header) {
        if (
          indicator.parentElement !== header ||
          indicator.nextElementSibling !== profileAnchor
        ) {
          header.insertBefore(indicator, profileAnchor);
        }
      } else if (indicator.parentElement !== header) {
        header.append(indicator);
      }
    } finally {
      syncing = false;
    }
  };

  syncInstalledIndicator = sync;
  const observer = new MutationObserver(() => {
    if (vpnConnected) {
      sync();
    }
  });
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
  sync();

  return () => {
    observer.disconnect();
    if (syncInstalledIndicator === sync) {
      syncInstalledIndicator = null;
    }
    indicator?.remove();
    removeIndicators();
  };
}
