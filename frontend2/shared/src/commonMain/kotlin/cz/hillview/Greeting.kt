package cz.hillview

class Greeting {
    private val platform = getPlatform()

    fun greet(): String {
        return "Running on ${platform.name}"
    }
}
