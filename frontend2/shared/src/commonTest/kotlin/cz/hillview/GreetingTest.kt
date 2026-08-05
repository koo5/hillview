package cz.hillview

import kotlin.test.Test
import kotlin.test.assertTrue

class GreetingTest {

    @Test
    fun greetingContainsPlatformName() {
        assertTrue(Greeting().greet().startsWith("Running on "))
    }
}
