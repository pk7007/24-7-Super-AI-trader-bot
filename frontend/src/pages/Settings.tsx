import { useContext } from "react";
import { Badge, KV, PageHead, Panel, Seg } from "../components/ui";
import { ThemeCtx, type Theme } from "../app/theme";

export default function Settings() {
  const { theme, setTheme } = useContext(ThemeCtx);
  return (
    <div className="page stack">
      <PageHead crumbs="System" title="Settings" lede="Display preferences for this browser. Trading settings are deliberately not editable here." />
      <div className="grid cols-2">
        <Panel title="Display">
          <KV
            items={[
              [
                "Theme",
                <Seg<Theme>
                  label="Theme"
                  value={theme}
                  onChange={setTheme}
                  options={[
                    { v: "dark", label: "Dark" },
                    { v: "light", label: "Light" },
                  ]}
                />,
              ],
              ["Stored in", <span className="mono">localStorage (atl.theme, atl.sidebar)</span>],
            ]}
          />
        </Panel>
        <Panel title="Data and safety">
          <KV
            items={[
              ["API", <span className="mono">127.0.0.1:8765, GET only</span>],
              ["Refresh", <span>30–60 s while this tab is visible</span>],
              ["Order entry", <Badge tone="outline">none, by design</Badge>],
              ["Live trading", <Badge tone="bad">disabled</Badge>],
              ["Risk configuration", <span>read-only; changed through code review</span>],
            ]}
          />
        </Panel>
      </div>
    </div>
  );
}
