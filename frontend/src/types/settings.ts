export type PlatformId = "linkedin" | "indeed" | "infojobs";

export interface PlatformConfig {
  readonly platform: PlatformId;
  readonly enabled: boolean;
  readonly label: string;
}

export interface AppSettings {
  readonly platforms: PlatformConfig[];
  readonly notifications_enabled: boolean;
}
