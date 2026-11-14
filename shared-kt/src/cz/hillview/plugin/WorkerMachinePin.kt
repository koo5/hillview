package cz.hillview.plugin

import org.json.JSONObject

/**
 * The Fly machine uploads are pinned to (`fly-force-instance-id`), and the
 * worker URL whose /ready named it. See PhotoUploadLogic.pinnedWorker.
 *
 * The URL is part of the pin because a machine id means something only behind
 * the edge that handed it out. Before 2026-11-09 the pin was a bare id, so it
 * outlived a switch of worker (an override set or cleared, or authorize-upload
 * naming another worker), and the new worker was sent the old one's machine.
 */
internal data class WorkerMachinePin(val workerUrl: String, val machineId: String)

/** The machine id to force on a request to [workerUrl]: the pin's, if it was learned there. */
internal fun WorkerMachinePin?.machineFor(workerUrl: String): String? =
	this?.takeIf { it.workerUrl == workerUrl }?.machineId

/**
 * The `fly_machine_id` of a /ready body, or null when there is none to pin to:
 * absent, JSON null (every worker not on Fly sends that), blank, or a body
 * that isn't JSON (an older worker's /health).
 *
 * Not `optString`: Android's org.json returns the STRING "null" for a JSON
 * null, so a worker off Fly got the phone pinned to a machine called "null"
 * — sent as `fly-force-instance-id: null` to whichever worker came next.
 */
internal fun readyMachineId(body: String?): String? {
	if (body.isNullOrBlank()) return null
	val json = try {
		JSONObject(body)
	} catch (e: Exception) {
		return null
	}
	if (!json.has("fly_machine_id") || json.isNull("fly_machine_id")) return null
	return (json.opt("fly_machine_id") as? String)?.takeIf { it.isNotBlank() }
}
