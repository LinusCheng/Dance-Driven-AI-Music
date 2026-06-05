class MagentaController:
    def connect(self) -> None:
        print('MagentaController: connect() called — placeholder for future RealTime 2 integration.')

    def update_music_state(self, music_state: dict) -> None:
        print('MagentaController: update_music_state() would send:', music_state)

    def shutdown(self) -> None:
        print('MagentaController: shutdown() called.')
