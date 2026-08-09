package cz.hillview

import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import cz.hillview.di.initKoin

fun main() {
    initKoin()
    application {
        Window(
            onCloseRequest = ::exitApplication,
            title = "Hillview",
        ) {
            App()
        }
    }
}
