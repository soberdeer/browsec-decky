import {
  afterPatch,
  findModuleDetailsByExport,
} from "@decky/ui";
import {
  Children,
  cloneElement,
  isValidElement,
  type ReactElement,
  type ReactNode,
  useEffect,
  useState,
} from "react";

import { BrowsecIcon } from "./BrowsecIcon";

const indicatorKey = "browsec-decky-connected-indicator";

let vpnConnected = false;
const connectionListeners = new Set<(connected: boolean) => void>();

export function setHeaderVpnConnected(connected: boolean) {
  if (vpnConnected === connected) {
    return;
  }

  vpnConnected = connected;
  for (const listener of connectionListeners) {
    listener(connected);
  }
}

function useVpnConnected() {
  const [connected, setConnected] = useState(vpnConnected);

  useEffect(() => {
    connectionListeners.add(setConnected);
    setConnected(vpnConnected);

    return () => {
      connectionListeners.delete(setConnected);
    };
  }, []);

  return connected;
}

function ConnectedHeaderIndicator() {
  const connected = useVpnConnected();

  if (!connected) {
    return null;
  }

  return (
    <div
      aria-label="Browsec VPN connected"
      data-browsec-decky-status="connected"
      role="status"
      style={{
        alignItems: "center",
        color: "inherit",
        display: "flex",
        flexShrink: 0,
        height: "28px",
        justifyContent: "center",
        width: "28px",
      }}
      title="Browsec VPN connected"
    >
      <BrowsecIcon
        style={{
          height: "22px",
          width: "22px",
        }}
      />
    </div>
  );
}

function getHeaderRender(value: unknown) {
  if (typeof value === "function") {
    return value;
  }

  if (
    typeof value === "object" &&
    value !== null &&
    "type" in value &&
    typeof value.type === "function"
  ) {
    return value.type;
  }

  return null;
}

function isGameModeHeader(value: unknown) {
  const render = getHeaderRender(value);
  if (!render) {
    return false;
  }

  const source = render.toString();
  return (
    source.includes("quickAccessHeader") &&
    source.includes("BShowHeader")
  );
}

interface ElementWithChildren {
  children?: ReactNode;
}

function addIndicatorToHeader(
  _args: unknown[],
  result: unknown,
): unknown {
  if (!isValidElement<ElementWithChildren>(result)) {
    return result;
  }

  const header = result.props.children;
  if (!isValidElement<ElementWithChildren>(header)) {
    return result;
  }

  const children = Children.toArray(header.props.children);
  const indicator = (
    <ConnectedHeaderIndicator key={indicatorKey} />
  );
  const patchedHeader = cloneElement(
    header as ReactElement<ElementWithChildren>,
    undefined,
    [...children, indicator],
  );

  return cloneElement(
    result as ReactElement<ElementWithChildren>,
    undefined,
    patchedHeader,
  );
}

export function installHeaderIndicator() {
  const [module, headerExport, exportName] =
    findModuleDetailsByExport(isGameModeHeader);

  if (!module || !headerExport || exportName === undefined) {
    console.warn(
      "[Browsec Decky] Could not find the Steam Game Mode header",
    );
    return () => {};
  }

  const render = getHeaderRender(headerExport);
  if (!render) {
    return () => {};
  }

  const patch =
    typeof headerExport === "function"
      ? afterPatch(module, String(exportName), addIndicatorToHeader)
      : afterPatch(headerExport, "type", addIndicatorToHeader);

  return () => {
    if (!patch.hasUnpatched) {
      patch.unpatch();
    }
  };
}
