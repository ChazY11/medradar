/** Whether this build is being served by the public alpha deployment. */
declare global {
  interface Window {
    __MEDRADAR_ALPHA__?: boolean;
  }
}

export const IS_PUBLIC_ALPHA =
  typeof window !== "undefined" && window.__MEDRADAR_ALPHA__ === true;
