import customtkinter as ctk


class Separator(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, height=1, fg_color="#444444", **kwargs)
