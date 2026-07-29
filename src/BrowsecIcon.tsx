import type { SVGProps } from "react";

export const browsecIconPath =
  "M5.82 9.874c3.102 13.353 9.86 24.519 19.557 33.964 9.72-9.445 16.455-20.611 19.602-33.964-10.507-3.257-20.968-3.676-31.451-1.792 2.152 8.375 6.017 16.308 11.849 23.729 3.75-4.49 6.873-9.748 9.257-15.912-6.156-1.117-12.289-1.094-18.445 0";

export function BrowsecIcon({
  style,
  ...props
}: SVGProps<SVGSVGElement>) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      focusable="false"
      height="1em"
      viewBox="0 0 50.8 50.8"
      width="1em"
      {...props}
      style={{
        display: "block",
        flexShrink: 0,
        ...style,
      }}
    >
      <path
        d={browsecIconPath}
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="3.175"
      />
    </svg>
  );
}
