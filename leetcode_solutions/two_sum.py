from typing import Optional

class Solution:
    def twoSum(self, nums: list[int], target: int) -> list[int]:
        preMap = {}
        for i, num in enumerate(nums):
            diff = target - num
            if diff in preMap:
                return [preMap[diff], i]
            preMap[num] = i
        return []

if __name__ == "__main__":
    print(Solution().twoSum([2, 7, 11, 15], 9))
