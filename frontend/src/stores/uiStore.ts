import { writable } from 'svelte/store';
import type { NotificationState } from '../lib/types.js';

// UI state management
export const notifications = writable<NotificationState[]>([]);
export const isRefreshing = writable<boolean>(false);
export const lastUpdate = writable<Date | null>(null);

let notificationId = 0;

interface UiActions {
	showNotification: (message: string, type?: NotificationState['type'], duration?: number) => number;
	removeNotification: (id: number) => void;
	clearNotifications: () => void;
	setRefreshing: (state: boolean) => void;
}

export const uiActions: UiActions = {
	showNotification(message: string, type: NotificationState['type'] = 'info', duration: number = 4000): number {
		const id = ++notificationId;
		const notification: NotificationState = {
			id: id.toString(),
			message,
			type,
			duration,
			timestamp: Date.now()
		};

		notifications.update(items => [...items, notification]);

		if (duration > 0) {
			setTimeout(() => {
				uiActions.removeNotification(id);
			}, duration);
		}

		return id;
	},

	removeNotification(id: number): void {
		notifications.update(items => items.filter(item => item.id !== id.toString()));
	},

	clearNotifications(): void {
		notifications.set([]);
	},

	setRefreshing(state: boolean): void {
		isRefreshing.set(state);
		if (!state) {
			lastUpdate.set(new Date());
		}
	}
};