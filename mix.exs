defmodule Pusher.MixProject do
  use Mix.Project

  def project do
    [
      apps_path: "apps",
      apps: [
        :core,
        :picker,
        :control
      ],
      releases: [
        my_release: [
          applications: [
            core: :permanent,
            picker: :permanent,
            control: :permanent
          ],
          overlays: ["envs/"],
          path: "_build/rel"
        ]
      ],
      version: "0.1.0",
      start_permanent: Mix.env() == :dev,
      deps: deps()
    ]
  end

  # Dependencies listed here are available only for this
  # project and cannot be accessed from applications inside
  # the apps folder.
  #
  # Run "mix help deps" for examples and options.
  defp deps do
    []
  end
end
