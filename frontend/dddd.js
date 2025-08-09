/*let's design a new photo.worker.ts.
It will have async processor functions for individual message types. make sure to use photoProcessingUtils.ts in it. It will have a loop, and will store the last data received (such as the current state of sources, current bearing, current area), and it will ensure that: when handleMessage is called, if the processor function is not currently running, the current data will be updated from the message, and it will be started immediately. If a processor is running, the worker will set its aborted state to true (which the processor function can optionally read to abort itself), and then, when the processor message is finished, it will run it again if there is new data. The priorities will be: 1) sources update 2) area update 3) bearing update. It must ensure that at all times, only one instance of the async processor funnction is running, it must always wait for it to end before updating current data or running any processor function. It must not run it if it was already ran with the same data (each message can be assigned a sequential ID). It must ensure that if it was not ran with the latest data, it will be ran as soon as the current instance finishes. Only the latest data matters, intermediate values will be overwritten, but we must not overwrite the current valuee while any processor function is running. We must ensure that only one processor function is processing at a time. Multiple async processor functions cannot run concurrently.

Effectively, it could be implemented something like this:
*/

messageIdCounter = 0;

function enqueueInternal(messageType) {
	handleMessage({ type: messageType, internal: true});
}

const processors = new Processors(enqueueInternal);

const endings = new MessageQueue();
const messageQueue = new MessageQueue();
let currentProcessor = null;

function handleMessage(message) {
	// Add the message to the queue
	messageQueue.addMessage({...message, id: messageIdCounter++});
}



async function loop() {
	while (true) {
		// sleep until next message

		while (true) {
			// process abortions and data updates for all accumulated messages

			let message;

			if (processors.data.config.lastUpdateId === processors.data.config.lastProcessedId &&
				processors.data.sources.lastUpdateId === processors.data.sources.lastProcessedId &&
                processors.data.area.lastUpdateId === processors.data.area.lastProcessedId &&
                processors.data.bearing.lastUpdateId === processors.data.bearing.lastProcessedId) {
				// nothing to do, sleep until next message
				message = await messageQueue.getNextMessage();
			}
			else {
				if (messageQueue.hasMore()) {
					message = await messageQueue.getNextMessage();
				} else {
					break;
				}
			}

			const p = currentProcessor;
			if (p) {
				if (message.type === 'configUpdated') {
					if (p === 'configUpdated' || p === 'sourcesUpdated' || p === 'areaUpdated' || p === 'bearingUpdated') {
						await abortCurrentProcessor();
						if (!message.internal)
						processors.data.config.current = message.data.config;
						processors.data.config.lastUpdateId = message.data.id;
					}
				}
				else if (message.type === 'sourcesUpdated') {
					if (p === 'sourcesUpdated' || p === 'areaUpdated' || p === 'bearingUpdated') {
						await abortCurrentProcessor();
						if (!message.internal)
						processors.data.sources.current = message.data.sources;
						processors.data.sources.lastUpdateId = message.data.id;
					}
				} else if (message.type === 'areaUpdated') {
					if (p === 'areaUpdated' || p === 'bearingUpdated') {
						await abortCurrentProcessor();
						if (!message.internal)
						processors.data.area.current = message.data.area;
						processors.data.area.lastUpdateId = message.data.id;
					}
				} else if (message.type === 'bearingUpdated') {
					if (p === 'bearingUpdated') {
						await abortCurrentProcessor();
						if (!message.internal)
						processors.data.bearing.current = message.data.bearing;
						processors.data.bearing.lastUpdateId = message.data.id;
					}
				} else if (message.type === 'exit') {
					return;
				}
			}
			if (!messageQueue.hasMore()) {
				break;
			}
		}

		endings.clear();
		assert(!currentProcessor, 'There should be no current processor at this point');

		// run the relevant processors by priority
		if (processors.data.config.lastUpdateId !== processors.data.config.lastProcessedId) {
			await startProcessor('configUpdated', processors.data.config.lastUpdateId);
		} else if (processors.data.sources.lastUpdateId !== processors.data.sources.lastProcessedId) {
			await startProcessor('sourcesUpdated', processors.data.sources.lastUpdateId);
		} else if (processors.data.area.lastUpdateId !== processors.data.area.lastProcessedId) {
			await startProcessor('areaUpdated', processors.data.area.lastUpdateId);
		} else if (processors.data.bearing.lastUpdateId !== processors.data.bearing.lastProcessedId) {
			await startProcessor('bearingUpdated', processors.data.bearing.lastUpdateId);
		}
	}
}

async function abortCurrentProcessor() {
	processors.aborted = true;
	await endings.getNextMessage();
	processors.aborted = false;
}

async function startProcessor(type, messageId) {
	currentProcessor = type;
	startProcessor2(type, messageId);
}

async function startProcessor2(type, messageId) {
	try {
		if (type === 'configUpdated') {
			await processors.configUpdated();
		if (type === 'sourcesUpdated') {
			await processors.sourcesUpdated();
		} else if (type === 'areaUpdated') {
			await processors.areaUpdated();
		} else if (type === 'bearingUpdated') {
			await processors.bearingUpdated();
		}
		else {
			throw new Error(`Unknown processor type: ${type}`);
		}
		processors.data.sources.lastProcessedId = messageId;
	} catch (error) {
		console.error('Error processing sourcesUpdated message:', error);
	} finally {
		currentProcessor = null;
		endings.addMessage(true);
	}
}