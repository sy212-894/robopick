"""robomimic hdf5 데이터셋의 구조를 요약한다 (0단계 환경 확인용).

사용: python inspect_dataset.py <hdf5 경로>
"""
import json
import sys

import h5py
import numpy as np


def main(path: str) -> None:
    with h5py.File(path, "r") as f:
        data = f["data"]
        demos = sorted(data.keys(), key=lambda k: int(k.split("_")[1]))
        lengths = np.array([data[d].attrs["num_samples"] for d in demos])
        print(f"시범 수: {len(demos)}")
        print(f"총 샘플 수(data.attrs['total']): {data.attrs.get('total')}")
        print(f"길이: 최소 {lengths.min()}, 평균 {lengths.mean():.1f}, 중앙값 {np.median(lengths):.0f}, 최대 {lengths.max()}")

        print("\n[필터 키 (mask)]")
        if "mask" in f:
            for k in sorted(f["mask"].keys()):
                print(f"  {k}: {len(f['mask'][k][()])}개")
        else:
            print("  없음")

        d0 = data[demos[0]]
        print(f"\n[{demos[0]} 구조]")
        for k in d0.keys():
            item = d0[k]
            if isinstance(item, h5py.Group):
                print(f"  {k}/")
                for kk in item.keys():
                    print(f"    {kk}: {item[kk].shape} {item[kk].dtype}")
            else:
                print(f"  {k}: {item.shape} {item.dtype}")
        print(f"  attrs: {list(d0.attrs.keys())}")

        if "object" in d0["obs"]:
            obj0 = d0["obs"]["object"][0]
            print(f"\n[첫 프레임 object 상태 (demo_0)] 차원 {obj0.shape[0]}")
            print("  " + np.array2string(obj0, precision=3, suppress_small=True))

        env_args = json.loads(data.attrs["env_args"])
        print("\n[환경 정보 env_args]")
        print(f"  env_name: {env_args.get('env_name')}, type: {env_args.get('type')}")
        kw = env_args.get("env_kwargs", {})
        for k in ["robots", "controller_configs", "horizon", "control_freq", "reward_shaping", "use_object_obs", "use_camera_obs"]:
            v = kw.get(k)
            if k == "controller_configs" and isinstance(v, dict):
                v = v.get("type")
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main(sys.argv[1])
