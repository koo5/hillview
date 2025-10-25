export class AuthTokenManager {
    private authTokenPromise: Promise<string | null> | undefined;
    private authTokenPromiseResolve: ((value: string | null) => void) | undefined;
    private postMessageToFrontend: (message: any) => void;

    constructor(postMessageToFrontend: (message: any) => void) {
        this.postMessageToFrontend = postMessageToFrontend;
    }

    async getValidToken(forceRefresh: boolean = false): Promise<string | null> {
        // Return existing promise if we have one
        if (this.authTokenPromise) {
            return this.authTokenPromise;
        }

        this.authTokenPromise = new Promise<string | null>((resolve) => {
            this.authTokenPromiseResolve = resolve;
            this.postMessageToFrontend({
                type: 'getAuthToken',
                forceRefresh
            });
        });

        return this.authTokenPromise;
    }

    resolveTokenPromise(token: string | null): void {
        if (this.authTokenPromiseResolve) {
            this.authTokenPromiseResolve(token);
            this.authTokenPromiseResolve = undefined;
            this.authTokenPromise = undefined; // Clear promise for next request
            console.log('AuthTokenManager: Token promise resolved');
        } else {
            console.warn('AuthTokenManager: Received token but no pending promise to resolve');
        }
    }

    clearPendingPromise(): void {
        this.authTokenPromise = undefined;
        this.authTokenPromiseResolve = undefined;
        console.log('AuthTokenManager: Cleared pending promise');
    }
}