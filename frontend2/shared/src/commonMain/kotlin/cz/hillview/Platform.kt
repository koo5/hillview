package cz.hillview

interface Platform {
    val name: String
}

expect fun getPlatform(): Platform
