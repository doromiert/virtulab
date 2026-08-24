{
  description = "MikroTik RB960PGS training lab with two Windows 11 clients";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};

      chrImage = pkgs.fetchurl {
        url = "https://download.mikrotik.com/routeros/7.24.1/chr-7.24.1.img.zip";
        sha256 = "1a0sgb53xp3anhi1ncbnvzkj4hmrj8mcscy9qvqj2hqnjw0myd2h";
      };

      winbox = pkgs.fetchurl {
        url = "https://download.mikrotik.com/routeros/winbox/4.3/WinBox_Windows.zip";
        sha256 = "02qh6rprblx9lnkgij72f5kc3ldnjflacarvn5iqy6vypqm2ip7j";
      };

      winboxLegacy = pkgs.fetchurl {
        url = "https://download.mikrotik.com/routeros/winbox/3.43/winbox64.exe";
        sha256 = "1sdn0yay1m11cx4dr3nzwqibljngb4hm4svzd21d1s41zm8wyhav";
      };

      lucide = pkgs.fetchurl {
        url = "https://unpkg.com/lucide@0.468.0/dist/umd/lucide.min.js";
        sha256 = "03i188rmm2jh3ks4d029yica60ynbyi6ljb97xa4g3fb40l6j49l";
      };

      source = pkgs.stdenvNoCC.mkDerivation {
        pname = "mikrotik-cable-lab-source";
        version = "1.0.0";
        src = pkgs.lib.cleanSourceWith {
          src = ./.;
          filter =
            path: type:
            let
              name = baseNameOf path;
            in
            name != "win11.iso" && name != "__pycache__" && name != ".pytest_cache";
        };
        installPhase = ''
          mkdir -p $out
          cp -R labctl.py web docs tests $out/
          cp ${lucide} $out/web/lucide.min.js
        '';
      };

      runtimeInputs = with pkgs; [
        python3
        libvirt
        qemu_kvm
        swtpm
        virt-viewer
        xorriso
      ];

      mkApp =
        name: command:
        pkgs.writeShellApplication {
          inherit name;
          runtimeInputs = runtimeInputs;
          text = ''
            export MIKROTIK_LAB_SOURCE=${source}
            export MIKROTIK_CHR_ARCHIVE=${chrImage}
            export MIKROTIK_WINBOX_ARCHIVE=${winbox}
            export MIKROTIK_WINBOX3_EXE=${winboxLegacy}
            exec python3 ${source}/labctl.py ${command} "$@"
          '';
        };

      labSetup = mkApp "mikrotik-lab-setup" "prepare";
      labUi = mkApp "mikrotik-lab-ui" "serve";
      labCtl = mkApp "mikrotik-lab" "";
    in
    {
      packages.${system} = {
        default = labCtl;
        setup = labSetup;
        ui = labUi;
      };

      apps.${system} = {
        default = {
          type = "app";
          program = "${labCtl}/bin/mikrotik-lab";
        };
        setup = {
          type = "app";
          program = "${labSetup}/bin/mikrotik-lab-setup";
        };
        ui = {
          type = "app";
          program = "${labUi}/bin/mikrotik-lab-ui";
        };
      };

      checks.${system}.tests =
        pkgs.runCommand "mikrotik-cable-lab-tests"
          {
            nativeBuildInputs = [ pkgs.python3 ];
          }
          ''
            cd ${source}
            python3 -m unittest discover -s tests -v
            touch $out
          '';

      devShells.${system}.default = pkgs.mkShell {
        packages = runtimeInputs ++ [ pkgs.nixfmt ];
        shellHook = ''
          export MIKROTIK_LAB_SOURCE=$PWD
          export MIKROTIK_CHR_ARCHIVE=${chrImage}
          export MIKROTIK_WINBOX_ARCHIVE=${winbox}
          export MIKROTIK_WINBOX3_EXE=${winboxLegacy}
        '';
      };

      formatter.${system} = pkgs.nixfmt;
    };
}
