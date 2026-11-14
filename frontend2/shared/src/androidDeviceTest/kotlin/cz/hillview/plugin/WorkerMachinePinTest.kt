package cz.hillview.plugin

import kotlin.test.assertEquals
import kotlin.test.assertNull
import org.junit.Test

/**
 * Worker machine pinning across a switch of worker (WorkerMachinePin.kt).
 *
 * A device test, not a host one, on purpose: the bug was Android's org.json,
 * whose optString returns "null" for a JSON null. Maven's org.json returns
 * the default instead, so a JVM test would pass against the broken code.
 */
class WorkerMachinePinTest {

	private val fly = "https://hillview-worker.fly.dev"
	private val aux = "https://aux.example/worker"

	@Test
	fun aWorkerOffFlyNamesNoMachine() {
		// What every worker without FLY_MACHINE_ID answers (worker app.py /ready).
		assertNull(readyMachineId("""{"status": "ready", "fly_machine_id": null, "pending_tasks": 0}"""))
		assertNull(readyMachineId("""{"status": "ready"}"""))
		assertNull(readyMachineId("""{"fly_machine_id": ""}"""))
		assertNull(readyMachineId("ok"), "an older worker's /health")
		assertNull(readyMachineId(null))
	}

	@Test
	fun theQuirkTheOldParsingFellFor() {
		// What the pre-2026-11-09 code did with an off-Fly worker's answer:
		// pinned to "null". If this ever stops holding, the platform changed,
		// not readyMachineId.
		val old = org.json.JSONObject("""{"fly_machine_id": null}""").optString("fly_machine_id")
		assertEquals("null", old)
	}

	@Test
	fun aFlyWorkerNamesItsMachine() {
		assertEquals("e784079b449483", readyMachineId("""{"status": "ready", "fly_machine_id": "e784079b449483"}"""))
	}

	@Test
	fun aPinIsSentOnlyToTheWorkerThatGaveIt() {
		val pin = WorkerMachinePin(fly, "e784079b449483")
		assertEquals("e784079b449483", pin.machineFor(fly))
		assertNull(pin.machineFor(aux), "switched to another worker: no Fly machine to force there")
		assertNull((null as WorkerMachinePin?).machineFor(fly))
	}
}
