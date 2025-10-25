export type ProcessType = 'config' | 'area' | 'sourcesPhotosInArea';

interface ProcessInfo {
    id: string;
    type: ProcessType;
    messageId: number;
    startTime: number;
    shouldAbort: boolean;
}

export class ProcessManager {
    private processTable = new Map<string, ProcessInfo>();
    private processIdCounter = 0;
    private processMonitorInterval: NodeJS.Timeout | null = null;

    // Process priority levels (higher number = higher priority)
    private readonly PROCESS_PRIORITY = {
        config: 3,
        area: 2,
        sourcesPhotosInArea: 1
    } as const;

    startProcess(type: ProcessType, messageId: number): string {
        const processId = this.createProcessId();

        // Mark conflicting processes for abortion
        this.markConflictingProcessesForAbortion(type);

        // Create process info
        const processInfo: ProcessInfo = {
            id: processId,
            type,
            messageId,
            startTime: Date.now(),
            shouldAbort: false
        };

        this.processTable.set(processId, processInfo);
        console.log(`ProcessManager: Started ${type} process ${processId}`);

        return processId;
    }

    shouldAbort(processId: string): boolean {
        const processInfo = this.processTable.get(processId);
        return processInfo?.shouldAbort || false;
    }

    cleanupProcess(processId: string): void {
        this.processTable.delete(processId);
        console.log(`ProcessManager: Cleaned up process ${processId}`);
    }

    hasActiveProcesses(): boolean {
        for (const [processId, processInfo] of this.processTable.entries()) {
            if (!processInfo.shouldAbort) {
                return true;
            }
        }
        return false;
    }

    abortAllProcesses(): void {
        for (const [processId, process] of this.processTable.entries()) {
            console.log(`ProcessManager: Aborting process ${processId}`);
            process.shouldAbort = true;
        }
    }

    clearAllProcesses(): void {
        this.processTable.clear();
        console.log('ProcessManager: Cleared all processes');
    }

    startProcessMonitor(): void {
        this.processMonitorInterval = setInterval(() => {
            this.logRunningProcesses();
        }, 10000);
        console.log('ProcessManager: Process monitor started (10s interval)');
    }

    stopProcessMonitor(): void {
        if (this.processMonitorInterval) {
            clearInterval(this.processMonitorInterval);
            this.processMonitorInterval = null;
            console.log('ProcessManager: Process monitor stopped');
        }
    }

    private createProcessId(): string {
        return `proc_${++this.processIdCounter}_${Date.now()}`;
    }

    private markConflictingProcessesForAbortion(newProcessType: ProcessType): void {
        const newPriority = this.PROCESS_PRIORITY[newProcessType];

        for (const [processId, processInfo] of this.processTable.entries()) {
            const existingPriority = this.PROCESS_PRIORITY[processInfo.type];

            // Only abort existing processes if new process has HIGHER priority
            if (newPriority > existingPriority) {
                console.log(`ProcessManager: Marking process ${processId} (${processInfo.type}) for abortion due to higher priority ${newProcessType} update`);
                processInfo.shouldAbort = true;
            }
        }
    }

    private logRunningProcesses(): void {
        const runningProcesses = [];
        const abortedProcesses = [];

        for (const [processId, processInfo] of this.processTable.entries()) {
            const duration = Date.now() - processInfo.startTime;
            const processData = {
                id: processId,
                type: processInfo.type,
                messageId: processInfo.messageId,
                duration: `${duration}ms`,
                shouldAbort: processInfo.shouldAbort
            };

            if (processInfo.shouldAbort) {
                abortedProcesses.push(processData);
            } else {
                runningProcesses.push(processData);
            }
        }

        if (runningProcesses.length > 0 || abortedProcesses.length > 0) {
            console.log(`ProcessManager: Process Monitor - Running: ${runningProcesses.length}, Aborting: ${abortedProcesses.length}`);

            if (runningProcesses.length > 0) {
                console.log('🢄  Active processes:', runningProcesses);
            }

            if (abortedProcesses.length > 0) {
                console.log('🢄  Aborting processes:', abortedProcesses);
            }
        }
    }
}