import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Tenderlitika",
    template: "%s | Tenderlitika",
  },
  description:
    "Tenderlitika помогает быстро оценить риски тендера, денежный разрыв и безопасную цену участия.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru">
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
