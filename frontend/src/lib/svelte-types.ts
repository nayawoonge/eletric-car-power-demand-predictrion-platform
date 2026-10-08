// Svelte component prop types
import type { ChargingStation, NotificationState } from './types.js';

// Component prop types
export interface AlertProps {
	notification: NotificationState;
}

export interface DashboardProps {
	stationId: string;
	station: ChargingStation | null;
}