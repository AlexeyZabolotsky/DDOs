# Pusher

High-performance server for time series analysis and network anomaly detection. Allows real-time response to events of abrupt changes in traffic structure, creation of control rules for FlowSpec and other infrastructure management agents.

## DEV

**[Home Page](https://antiddos-detector-apps.wb.ru)** | **[Real-time Events](https://antiddos-detector-apps.wb.ru/pusher_events)** | **[Application metrics](https://antiddos-detector-apps.wb.ru/stats)** | **[Live Dashboard](https://antiddos-detector-apps.wb.ru/dev/dashboard)**

## PROD

**[Home Page](http://antiddos-deep-learning-01.el.wb.ru:4000/)** | **[Real-time Events](http://antiddos-deep-learning-01.el.wb.ru:4000/pusher_events)** | **[Application metrics](http://antiddos-deep-learning-01.el.wb.ru:4000/stats)** | **[Live Dashboard](http://antiddos-deep-learning-01.el.wb.ru:4000/dev/dashboard)**


## Structure
Help for developers:

```
./apps # Here is source code
├── control/ # Frontends and help docs, links
├── core/ # Main app: fetchers, math, push rules logic
│   └── lib/ # Standard
│       └── core/
│           ├── fetchers/ # Where is the data from and how is it fetched
│           ├── flowspec/ # Everything you need to interact with FlowSpec
│           ├── marketing/ # Fetch marketing data (push events) - TBD impl model =)
│           ├── math/ # Math core - analysis & structures
│           ├── network/ # Utils for DNS and IP addresses and something else
│           ├── pipelines/ # What are called "detectors" are located here: pipelines for each type of data source
│           ├── plot/ # Plots, graphics (gnuplot) for telegram notifies
│           ├── senders/ # Anything that sends data somewhere out: clickhouses, kafka, telegram
│           ├── supports/ # Other utils and telemetry here (unstructured modules here)
│           ├── application.ex/ # Core application entry: all supervisors here 
│           └── sched.ex/ # Base genserver for "detectors" and other periodic tasks
├── picker # Directly from collector data flow
./config # Configs: dev/prod/runtime settings
./docs # Documentation space
./envs # Credentials/secrets as dot-files (.dev.env/.prod.env)
./tables.sql # Clickhouse tables, data models, maybe you need check it
./mix.exs # Mix build file, this project is "umbrella"-app, see [documentation](https://elixirschool.com/en/lessons/advanced/umbrella_projects)
```


## Setup new node
⚠️ For strict fault-tolerance, sub-millisecond latency, and real-time traffic analysis requirements, this system must run on bare metal—without Docker or Kubernetes. Containers and orchestration layers introduce unacceptable overhead for our use case. See [ADR-001](./docs/adr/001-en.md) for design rationale.

0. Install dependencies for OTP app

Libssl before build Erlang:
```
apt-get install libssl-dev
```

Also for plots you need install `gnuplot`:
```
apt-get install gnuplot
```

[Erlang/OTP](https://github.com/erlang/otp)
```
git clone https://github.com/erlang/otp.git
cd otp
git checkout maint-27
./configure
make
make install
```

[Elixir](https://github.com/elixir-lang/elixir)
```
git clone https://github.com/elixir-lang/elixir.git
cd elixir
git checkout v1.18.3
make
```

Hex & Rebar:
```
git clone git@gitlab-private.wildberries.ru:antiddos/pusher.git
cd pusher
mix local.hex --force
mix local.rebar --force
```

## How to release

1. Get dependencies

```
mix deps.get
```

2. Prepare assets for control app (Phoenix):

```
mix assets.deploy
```

3. Build release with your env

! check .{dev|prod}.env in ./envs/

```
MIX_ENV=prod mix release
```

4a. Restart the app
```
_build/rel/bin/my_release restart
```

4b. Hot code reload

You need build release with new version (SemVer). For example:
```
MIX_ENV=prod mix release --version=1.0.0

```
Structure of dirs:

```
/opt/my_app
├── releases/
│   ├── 1.0.0/
│   ├── 1.0.1/  # New version!
├── current -> /opt/my_app/releases/1.0.0  # Simlink
```

Upgrade:
```
/opt/my_app/bin/my_app upgrade 1.0.1
```

The application will continue to run, but new calls will use the updated code!
Old processes are terminated after the current tasks are completed **(graceful shutdown)**.


_Containers and orchestration are anti-patterns for real-time networking and break down the hot code reload feature._
