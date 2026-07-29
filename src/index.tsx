import {
  ButtonItem,
  DropdownItem,
  PanelSection,
  PanelSectionRow,
  TextField,
  staticClasses,
} from "@decky/ui";
import {
  addEventListener,
  callable,
  definePlugin,
  removeEventListener,
  toaster,
} from "@decky/api";
import { useCallback, useEffect, useState } from "react";

import logo from "../assets/logo.svg";

type TunnelStatus = "disconnected" | "connecting" | "connected";

interface Country {
  code: string;
  name: string;
  availability: number | null;
}

interface PublicState {
  loggedIn: boolean;
  email: string | null;
  premium: boolean;
  status: TunnelStatus;
  error: string | null;
  runtimeReady: boolean;
  selectedCountry: string | null;
  countries: Country[];
  publicIp: string | null;
}

const emptyState: PublicState = {
  loggedIn: false,
  email: null,
  premium: false,
  status: "disconnected",
  error: null,
  runtimeReady: false,
  selectedCountry: null,
  countries: [],
  publicIp: null,
};

const getState = callable<[], PublicState>("get_state");
const login = callable<[email: string, password: string], PublicState>("login");
const refresh = callable<[], PublicState>("refresh");
const selectCountry = callable<[country: string], PublicState>("select_country");
const connect = callable<[], PublicState>("connect");
const disconnect = callable<[], PublicState>("disconnect");
const logout = callable<[], PublicState>("logout");

function ErrorBox({ message }: { message: string }) {
  return (
    <div
      style={{
        background: "rgba(195, 55, 55, 0.22)",
        border: "1px solid rgba(255, 125, 125, 0.55)",
        borderRadius: "4px",
        color: "#ffd3d3",
        lineHeight: 1.35,
        padding: "10px 12px",
        width: "100%",
      }}
    >
      {message}
    </div>
  );
}

function StatusCard({ state }: { state: PublicState }) {
  const color =
    state.status === "connected"
      ? "#60d394"
      : state.status === "connecting"
        ? "#f7c948"
        : "#aeb6c2";
  const label =
    state.status === "connected"
      ? "Protected"
      : state.status === "connecting"
        ? "Connecting…"
        : "Not connected";

  return (
    <div
      style={{
        alignItems: "center",
        background: "rgba(0, 0, 0, 0.18)",
        borderRadius: "6px",
        display: "flex",
        gap: "12px",
        padding: "12px",
        width: "100%",
      }}
    >
      <img
        alt=""
        src={logo}
        style={{
          height: "30px",
          width: "30px",
        }}
      />
      <div>
        <div style={{ color, fontSize: "16px", fontWeight: 600 }}>{label}</div>
        <div style={{ color: "#c6d0dc", fontSize: "12px", marginTop: "2px" }}>
          {state.publicIp ? `VPN IP: ${state.publicIp}` : "All Game Mode traffic"}
        </div>
      </div>
    </div>
  );
}

function Content() {
  const [state, setState] = useState<PublicState>(emptyState);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(true);

  const execute = useCallback(
    async (action: () => Promise<PublicState>, clearPassword = false) => {
      setBusy(true);
      try {
        const next = await action();
        setState(next);
        if (clearPassword) {
          setPassword("");
        }
      } catch (error) {
        toaster.toast({
          title: "Browsec Decky",
          body: error instanceof Error ? error.message : "The operation failed",
        });
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  useEffect(() => {
    let active = true;
    const listener = addEventListener<[next: PublicState]>(
      "state_changed",
      (next) => {
        if (active) {
          setState(next);
        }
      },
    );
    getState()
      .then((next) => {
        if (active) {
          setState(next);
        }
      })
      .catch(() => {
        if (active) {
          setState((current) => ({
            ...current,
            error: "Could not reach the Browsec Decky backend",
          }));
        }
      })
      .finally(() => {
        if (active) {
          setBusy(false);
        }
      });
    return () => {
      active = false;
      removeEventListener("state_changed", listener);
    };
  }, []);

  if (!state.loggedIn) {
    return (
      <>
        <PanelSection title="Browsec Premium">
          {state.error && (
            <PanelSectionRow>
              <ErrorBox message={state.error} />
            </PanelSectionRow>
          )}
          <PanelSectionRow>
            <TextField
              disabled={busy}
              label="Email"
              mustBeEmail
              onChange={(event) => setEmail(event.currentTarget.value)}
              value={email}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <TextField
              bIsPassword
              disabled={busy}
              label="Password"
              onChange={(event) => setPassword(event.currentTarget.value)}
              value={password}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem
              disabled={busy || !email.trim() || !password}
              layout="below"
              onClick={() =>
                execute(() => login(email.trim(), password), true)
              }
            >
              {busy ? "Signing in…" : "Sign in"}
            </ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <div style={{ color: "#aeb6c2", fontSize: "12px", lineHeight: 1.4 }}>
              Browsec Desktop VPN currently requires a Premium account. Your
              password is sent directly to Browsec and is never stored.
            </div>
          </PanelSectionRow>
        </PanelSection>
      </>
    );
  }

  const isConnected = state.status === "connected";
  const isTransitioning = state.status === "connecting";
  const locationOptions = state.countries.map((country) => ({
    data: country.code,
    label: country.name,
  }));

  return (
    <>
      <PanelSection title="VPN">
        <PanelSectionRow>
          <StatusCard state={state} />
        </PanelSectionRow>
        {state.error && (
          <PanelSectionRow>
            <ErrorBox message={state.error} />
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <DropdownItem
            description="VPN exit location"
            disabled={busy || isTransitioning || isConnected}
            label="Location"
            onChange={(option) =>
              execute(() => selectCountry(String(option.data)))
            }
            rgOptions={locationOptions}
            selectedOption={state.selectedCountry}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            disabled={
              busy ||
              isTransitioning ||
              (!isConnected &&
                (!state.runtimeReady || !state.selectedCountry))
            }
            layout="below"
            onClick={() => execute(isConnected ? disconnect : connect)}
          >
            {isTransitioning
              ? "Connecting…"
              : isConnected
                ? "Disconnect"
                : "Connect"}
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
      <PanelSection title="Account">
        <PanelSectionRow>
          <div style={{ color: "#d8dee7", fontSize: "13px", width: "100%" }}>
            {state.email}
            <span style={{ color: "#60d394", float: "right" }}>Premium</span>
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            disabled={busy || isTransitioning || isConnected}
            onClick={() => execute(refresh)}
          >
            Refresh locations
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            disabled={busy || isTransitioning}
            onClick={() => execute(logout)}
          >
            Sign out
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}

export default definePlugin(() => {
  return {
    name: "Browsec Decky",
    titleView: (
      <div
        className={staticClasses.Title}
        style={{ alignItems: "center", display: "flex", gap: "8px" }}
      >
        <img
          alt=""
          src={logo}
          style={{
            height: "24px",
            width: "24px",
          }}
        />
        Browsec
      </div>
    ),
    content: <Content />,
    icon: (
      <img
        alt="Browsec"
        src={logo}
        style={{
          height: "24px",
          width: "24px",
        }}
      />
    ),
    onDismount() {},
  };
});
