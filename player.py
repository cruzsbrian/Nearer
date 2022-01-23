from typing import NamedTuple
import logging

import pafy
import vlc


logger = logging.getLogger(__name__)


class NearerSong(NamedTuple):
    url: str
    title: str
    thumb: str
    thumb_big: str


class Player:
    def __init__(self, song_end):
        """
        song_end: function to call after each song finishes
        """

        self.song_end_callback = song_end

        self.all_songs = []
        self.current_song_idx = 0

        # Create a new VLC MediaListPlayer and MediaList.
        vlc_instance = vlc.Instance()
        self.vlc_player = vlc_instance.media_list_player_new()
        self.vlc_list = vlc_instance.media_list_new()
        self.vlc_player.set_media_list(self.vlc_list)

        # Attach self.song_ended to the end reached event for the player.
        # Note: libvlc is not reentrant, so self.song_ended cannot call a libvlc function directly
        player_events = self.vlc_player.get_media_player().event_manager()
        player_events.event_attach(vlc.EventType.MediaPlayerEndReached, self.song_ended)

    def toggle_pause(self):
        logger.info("toggling pause")
        self.vlc_player.pause()

    def next(self):
        """
        Skip the current song.
        If the queue is not already exhausted, increments current_song_idx and
        tells VLC to either go to the next song or stop playing.
        """

        # If queue is already exhausted (should be playing nothing) do nothing
        if self.queue_exhausted():
            logger.info("queue is exhausted, ignoring next call")
        else:
            logger.info(f"skipping song {self.current_song_idx} of {len(self.all_songs)}")
            self.current_song_idx += 1

            if self.queue_exhausted():
                logger.info("last song was skipped, stopping player")
                self.vlc_player.stop()
            else:
                self.vlc_player.next()

    def add_song(self, url):
        """
        Get a video from youtube using pafy.
        Add the audio stream url to the VLC MediaList.
        Add a NearerSong with info to all_songs.
        If the queue is exhausted, start playing from this song.
        """

        video = pafy.new(url)
        best_audio = video.getbestaudio()

        self.vlc_list.add_media(best_audio.url)

        # Before adding to all_songs, check if the queue was exhausted. If it was, start playing this song.
        if self.queue_exhausted():
            # Use play_item_at_index() because if the player had stopped calling play() would make it start from the beginning.
            self.vlc_player.play_item_at_index(self.current_song_idx)

        self.all_songs.append(NearerSong(url, video.title, video.thumb, video.bigthumbhd))

        logger.info(f"added '{video.title}' as song {len(self.all_songs) - 1}")

    def song_ended(self, event):
        """
        Callback for VLC MediaPlayerEndReached event.
        Increment current_song_idx and call self.song_end_callback()
        """

        logger.info(f"song {self.current_song_idx} of {len(self.all_songs)} finished")
        self.current_song_idx += 1
        self.song_end_callback()

    def queue_exhausted(self):
        """
        Check if all songs in all_songs have already played
        """

        return self.current_song_idx >= len(self.all_songs)

    def print_info(self):
        song = self.all_songs[self.current_song_idx]
        print(song.title)
        print("thumb:", song.thumb)
        print("thumb_big:", song.thumb_big)
        print(f"time {self.vlc_player.get_media_player().get_time()} / {self.vlc_player.get_media_player().get_length()}")

    def print_queue(self):
        print(f"current song: {self.current_song_idx} of {len(self.all_songs)}")
        for i in range(len(self.all_songs)):
            if i == self.current_song_idx:
                print("-", self.all_songs[i].title)
            else:
                print(" ", self.all_songs[i].title)