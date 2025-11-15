// src/lib/remoteStore.ts
import { writable, type Subscriber, type Unsubscriber } from "svelte/store";

export type RemoteState<T> = {
	value: T | undefined;     // allows undefined default
	initialized: boolean;      // backend load finished (success or fail)
	loading: boolean;          // true while loading or saving
	error: unknown;            // backend error (if any)
};

export type RemoteStore<T> = {
	subscribe: (run: Subscriber<RemoteState<T>>) => Unsubscriber;
	/** Locally mutate value (not saved) */
	setValue(v: T | undefined): void;
	/** Reload from backend */
	refresh(): Promise<void>;
	/** Save value to backend */
	persist(v?: T): Promise<void>;
};

export function createRemoteStore<T>(opts: {
	initial?: T;                     // may be undefined
	load: () => Promise<T>;          // load from backend
	save: (value: T) => Promise<void>; // save to backend
	autoLoadOnSubscribe?: boolean;   // default true
}): RemoteStore<T> {
	const {
		initial = undefined,
		load,
		save,
		autoLoadOnSubscribe = true
	} = opts;

	let state: RemoteState<T> = {
		value: initial,
		initialized: false,
		loading: false,
		error: null
	};

	const store = writable<RemoteState<T>>(state, (set) => {
		let cancelled = false;

		if (autoLoadOnSubscribe) {
			(async () => {
				set({ ...state, loading: true });

				try {
					const value = await load();
					if (cancelled) return;

					state = {
						value,
						initialized: true,
						loading: false,
						error: null
					};
					set(state);
				} catch (err) {
					if (cancelled) return;

					state = {
						...state,
						initialized: true,
						loading: false,
						error: err
					};
					set(state);
				}
			})();
		}

		// STOP — last subscriber unsubscribed
		return () => {
			cancelled = true;
		};
	});

	const { subscribe, set, update } = store;

	function setValue(value: T | undefined) {
		update((s) => {
			state = { ...s, value };
			return state;
		});
	}

	async function refresh() {
		update((s) => {
			state = { ...s, loading: true, error: null };
			return state;
		});

		try {
			const value = await load();
			state = {
				value,
				initialized: true,
				loading: false,
				error: null
			};
			set(state);
		} catch (err) {
			update((s) => {
				state = { ...s, loading: false, error: err, initialized: true };
				return state;
			});
		}
	}

	// ❗ Pessimistic: value updates only after save() succeeds
	async function persist(provided?: T) {
		const valueToSave =
			provided !== undefined ? provided : state.value;

		// If value is undefined and no provided value, don’t save
		if (valueToSave === undefined) {
			throw new Error("Cannot persist undefined value");
		}

		update((s) => {
			state = { ...s, loading: true, error: null };
			return state;
		});

		try {
			await save(valueToSave);

			update((s) => {
				state = { ...s, value: valueToSave, loading: false };
				return state;
			});
		} catch (err) {
			update((s) => {
				state = { ...s, loading: false, error: err };
				return state;
			});
			throw err;
		}
	}

	return { subscribe, setValue, refresh, persist };
}
